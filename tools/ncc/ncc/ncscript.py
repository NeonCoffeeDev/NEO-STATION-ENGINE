"""NCScript -- a GDScript-shaped language that compiles to C.

The PS1 cannot run GDScript. Godot's runtime is tens of megabytes of C++ with a
garbage-collected VM; the console has 2 MB of RAM and no FPU. But *translating* a
restricted subset to C at build time costs nothing at run time -- the same MIPS
compiler that builds the engine builds your logic, and it ends up as native code.

So this is a transpiler, not an interpreter.

What it supports
----------------
    var speed: int = 20              module-level and local variables
    func _ready():                   called once when the scene starts
    func _update():                  called every frame
    func my_own(a, b):               your own functions
    if / elif / else, while, for i in range(n)
    + - * / %, comparisons, and / or / not
    calls into the engine API (see API in ncc/ncscript_api.py)

What it deliberately refuses
----------------------------
    floats           there is no FPU; use ints, or fixed-point where you need
                     fractions (4096 = 1.0)
    arrays, dicts    they need dynamic allocation
    classes          no object model on the console
    strings          beyond literals passed to print()

Every rejection is a clear error with a line number, because a transpiler that
silently drops code you wrote would be worse than no transpiler at all.
"""

import re

INDENT_UNIT = None          # inferred from the first indented line

KEYWORDS = {
    "var", "func", "if", "elif", "else", "while", "for", "in", "range",
    "return", "pass", "break", "continue", "and", "or", "not", "true", "false",
}

BANNED = {
    "float": "there is no FPU on the PS1. Use int, or fixed point where 4096 = 1.0",
    "class": "NCScript has no object model",
    "class_name": "NCScript has no object model",
    "extends": "NCScript has no inheritance",
    "signal": "no signals; call a function directly",
    "await": "no coroutines",
    "yield": "no coroutines",
    "Array": "no dynamic arrays",
    "Dictionary": "no dictionaries",
    "Vector2": "no vector types yet; use separate int variables",
    "Vector3": "no vector types yet; use separate int variables",
}


class ScriptError(Exception):
    def __init__(self, line, msg):
        super().__init__(f"line {line}: {msg}")
        self.line = line
        self.msg = msg


# ---- tokenizer ----------------------------------------------------------

TOKEN_RE = re.compile(r"""
    (?P<NUMBER>\d+)
  | (?P<NAME>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<STRING>"[^"\n]*")
  | (?P<OP>==|!=|<=|>=|[-+*/%<>()=,:])
  | (?P<SPACE>[ \t]+)
  | (?P<COMMENT>\#.*)
""", re.VERBOSE)


class Token:
    def __init__(self, kind, value, line):
        self.kind = kind
        self.value = value
        self.line = line

    def __repr__(self):
        return f"{self.kind}:{self.value}"


def tokenize(src):
    """Produce tokens with INDENT/DEDENT/NEWLINE, Python-style."""
    tokens = []
    indents = [0]
    depth = 0                                 # open parentheses carried over
    lineno = 1
    for lineno, raw in enumerate(src.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue                          # blank and comment-only lines

        # A line that continues an unclosed call carries no indentation meaning,
        # so a call may be wrapped across lines the way it can in GDScript.
        if depth == 0:
            indent = len(raw) - len(raw.lstrip())
            # Inspect the actual leading whitespace: lstrip() removes tabs too,
            # so checking the stripped string could never find them.
            if "\t" in raw[:indent]:
                raise ScriptError(lineno, "use spaces, not tabs, for indentation")

            if indent > indents[-1]:
                indents.append(indent)
                tokens.append(Token("INDENT", "", lineno))
            while indent < indents[-1]:
                indents.pop()
                tokens.append(Token("DEDENT", "", lineno))
            if indent != indents[-1]:
                raise ScriptError(lineno, "inconsistent indentation")

        pos = 0
        line_body = raw.rstrip()
        while pos < len(line_body):
            m = TOKEN_RE.match(line_body, pos)
            if not m:
                raise ScriptError(lineno,
                                  f"cannot read {line_body[pos]!r}")
            pos = m.end()
            kind = m.lastgroup
            text = m.group()
            if kind in ("SPACE", "COMMENT"):
                continue
            if kind == "NUMBER":
                tokens.append(Token("NUMBER", int(text), lineno))
            elif kind == "NAME":
                if text in BANNED:
                    raise ScriptError(lineno,
                                      f"'{text}' is not supported -- {BANNED[text]}")
                tokens.append(Token("NAME", text, lineno))
            elif kind == "STRING":
                tokens.append(Token("STRING", text, lineno))
            else:
                if text == "(":
                    depth += 1
                elif text == ")":
                    depth -= 1
                    if depth < 0:
                        raise ScriptError(lineno, "unmatched ')'")
                tokens.append(Token("OP", text, lineno))

        # Only end the statement once every parenthesis is closed.
        if depth == 0:
            tokens.append(Token("NEWLINE", "", lineno))

    if depth != 0:
        raise ScriptError(lineno, "unclosed '(' -- a call is missing its ')'")

    while len(indents) > 1:
        indents.pop()
        tokens.append(Token("DEDENT", "", lineno if src else 1))
    tokens.append(Token("EOF", "", (lineno if src else 1)))
    return tokens


# ---- parser -------------------------------------------------------------

# Binary operator precedence, loosest first. Mapped straight to C, which shares
# the semantics for every operator here.
BINOPS = [
    (["or"], "||"),
    (["and"], "&&"),
    (["==", "!=", "<", ">", "<=", ">="], None),
    (["+", "-"], None),
    (["*", "/", "%"], None),
]


class Parser:
    def __init__(self, tokens, api):
        self.toks = tokens
        self.i = 0
        self.api = api
        self.globals = {}
        self.funcs = []
        self.scopes = []

    # -- token helpers --
    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        return t.kind == kind and (value is None or t.value == value)

    def accept(self, kind, value=None):
        if self.at(kind, value):
            return self.next()
        return None

    def expect(self, kind, value=None):
        t = self.peek()
        if not self.at(kind, value):
            want = value or kind
            got = t.value if t.value != "" else t.kind
            raise ScriptError(t.line, f"expected {want!r}, found {got!r}")
        return self.next()

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.next()

    # -- program --
    def parse(self):
        self.skip_newlines()
        while not self.at("EOF"):
            if self.at("NAME", "var"):
                name, expr, line = self.parse_var()
                if name in self.globals:
                    raise ScriptError(line, f"'{name}' declared twice")
                self.globals[name] = expr
            elif self.at("NAME", "func"):
                self.funcs.append(self.parse_func())
            else:
                t = self.peek()
                raise ScriptError(t.line,
                                  f"expected 'var' or 'func' at the top level, "
                                  f"found {t.value!r}")
            self.skip_newlines()
        return self.globals, self.funcs

    def parse_var(self):
        line = self.expect("NAME", "var").line
        name = self.expect("NAME").value
        if self.accept("OP", ":"):
            type_tok = self.expect("NAME")
            if type_tok.value != "int":
                raise ScriptError(type_tok.line,
                                  f"only 'int' variables are supported, not "
                                  f"'{type_tok.value}'")
        self.expect("OP", "=")
        expr = self.parse_expr()
        self.expect("NEWLINE")
        return name, expr, line

    def parse_func(self):
        line = self.expect("NAME", "func").line
        name = self.expect("NAME").value
        self.expect("OP", "(")
        params = []
        while not self.at("OP", ")"):
            p = self.expect("NAME").value
            if self.accept("OP", ":"):
                self.expect("NAME")           # type annotation, ignored
            params.append(p)
            if not self.accept("OP", ","):
                break
        self.expect("OP", ")")
        if self.accept("OP", ":") and self.at("NAME") and not self.at("NEWLINE"):
            # a return type annotation such as "-> int" is not GDScript syntax
            # here; a bare ':' ends the signature
            pass
        self.expect("NEWLINE")
        body = self.parse_block(set(params))
        return {"name": name, "params": params, "body": body, "line": line}

    def parse_block(self, scope_names):
        self.expect("INDENT")
        self.scopes.append(set(scope_names))
        stmts = []
        while not self.at("DEDENT") and not self.at("EOF"):
            stmts.append(self.parse_stmt())
            self.skip_newlines()
        self.expect("DEDENT")
        self.scopes.pop()
        return stmts

    def parse_stmt(self):
        t = self.peek()

        if self.at("NAME", "pass"):
            self.next(); self.expect("NEWLINE")
            return {"k": "pass"}

        if self.at("NAME", "break") or self.at("NAME", "continue"):
            kw = self.next().value
            self.expect("NEWLINE")
            return {"k": kw}

        if self.at("NAME", "return"):
            self.next()
            expr = None if self.at("NEWLINE") else self.parse_expr()
            self.expect("NEWLINE")
            return {"k": "return", "expr": expr}

        if self.at("NAME", "var"):
            name, expr, line = self.parse_var()
            self.scopes[-1].add(name)
            return {"k": "local", "name": name, "expr": expr, "line": line}

        if self.at("NAME", "if"):
            return self.parse_if()

        if self.at("NAME", "while"):
            self.next()
            cond = self.parse_expr()
            self.expect("OP", ":")
            self.expect("NEWLINE")
            return {"k": "while", "cond": cond, "body": self.parse_block(set())}

        if self.at("NAME", "for"):
            self.next()
            var = self.expect("NAME").value
            self.expect("NAME", "in")
            self.expect("NAME", "range")
            self.expect("OP", "(")
            start = self.parse_expr()
            end = None
            if self.accept("OP", ","):
                end = self.parse_expr()
            self.expect("OP", ")")
            self.expect("OP", ":")
            self.expect("NEWLINE")
            body = self.parse_block({var})
            return {"k": "for", "var": var, "start": start, "end": end,
                    "body": body, "line": t.line}

        # assignment or bare call
        if self.at("NAME") and self.peek(1).kind == "OP" and \
                self.peek(1).value == "=":
            name = self.next().value
            self.next()
            expr = self.parse_expr()
            self.expect("NEWLINE")
            return {"k": "assign", "name": name, "expr": expr, "line": t.line}

        expr = self.parse_expr()
        self.expect("NEWLINE")
        return {"k": "exprstmt", "expr": expr, "line": t.line}

    def parse_if(self):
        line = self.expect("NAME", "if").line
        cond = self.parse_expr()
        self.expect("OP", ":")
        self.expect("NEWLINE")
        body = self.parse_block(set())
        node = {"k": "if", "cond": cond, "body": body, "orelse": [], "line": line}

        self.skip_newlines()
        if self.at("NAME", "elif"):
            self.toks[self.i] = Token("NAME", "if", self.peek().line)
            node["orelse"] = [self.parse_if()]
        elif self.at("NAME", "else"):
            self.next()
            self.expect("OP", ":")
            self.expect("NEWLINE")
            node["orelse"] = self.parse_block(set())
        return node

    # -- expressions (precedence climbing) --
    def parse_expr(self, level=0):
        if level >= len(BINOPS):
            return self.parse_unary()
        ops, _ = BINOPS[level]
        node = self.parse_expr(level + 1)
        while True:
            t = self.peek()
            matched = None
            if t.kind == "OP" and t.value in ops:
                matched = t.value
            elif t.kind == "NAME" and t.value in ops:
                matched = t.value
            if matched is None:
                return node
            self.next()
            rhs = self.parse_expr(level + 1)
            node = {"k": "bin", "op": matched, "l": node, "r": rhs, "line": t.line}

    def parse_unary(self):
        t = self.peek()
        if (t.kind == "OP" and t.value == "-") or (t.kind == "NAME" and
                                                   t.value == "not"):
            self.next()
            return {"k": "un", "op": t.value, "v": self.parse_unary(),
                    "line": t.line}
        return self.parse_primary()

    def parse_primary(self):
        t = self.next()
        if t.kind == "NUMBER":
            return {"k": "num", "v": t.value, "line": t.line}
        if t.kind == "STRING":
            return {"k": "str", "v": t.value, "line": t.line}
        if t.kind == "OP" and t.value == "(":
            e = self.parse_expr()
            self.expect("OP", ")")
            return e
        if t.kind == "NAME":
            if t.value in ("true", "false"):
                return {"k": "num", "v": 1 if t.value == "true" else 0,
                        "line": t.line}
            if self.at("OP", "("):
                self.next()
                args = []
                while not self.at("OP", ")"):
                    args.append(self.parse_expr())
                    if not self.accept("OP", ","):
                        break
                self.expect("OP", ")")
                return {"k": "call", "name": t.value, "args": args,
                        "line": t.line}
            return {"k": "name", "v": t.value, "line": t.line}
        raise ScriptError(t.line, f"unexpected {t.value or t.kind!r}")


# ---- code generation ----------------------------------------------------

class Generator:
    def __init__(self, globals_, funcs, api, source_name):
        self.globals = globals_
        self.funcs = funcs
        self.api = api
        self.source_name = source_name
        self.user_funcs = {f["name"]: len(f["params"]) for f in funcs}
        self.out = []
        self.locals = []

    def emit(self, line="", indent=0):
        self.out.append("    " * indent + line if line else "")

    def generate(self):
        self.emit("/* Generated from %s by ncc. Do not edit -- edit the script."
                  % self.source_name)
        self.emit(" * NCScript is transpiled to C at build time, so this costs")
        self.emit(" * nothing at run time. */")
        self.emit()
        self.emit('#include "nc_script.h"')
        self.emit()

        for name, expr in self.globals.items():
            self.emit("static int %s = %s;" % (name, self.expr(expr)))
        if self.globals:
            self.emit()

        # Forward declarations, so scripts can call functions defined later.
        for f in self.funcs:
            if f["name"] not in ("_ready", "_update"):
                self.emit("static int %s(%s);" % (
                    f["name"],
                    ", ".join("int " + p for p in f["params"]) or "void"))
        if any(f["name"] not in ("_ready", "_update") for f in self.funcs):
            self.emit()

        for f in self.funcs:
            self.func(f)

        # The engine calls these two; provide empty ones if the script did not.
        names = {f["name"] for f in self.funcs}
        if "_ready" not in names:
            self.emit("void nc_script_ready(void) { }")
        if "_update" not in names:
            self.emit("void nc_script_update(void) { }")

        return "\n".join(self.out) + "\n"

    def func(self, f):
        name = f["name"]
        if name == "_ready":
            self.emit("void nc_script_ready(void)")
        elif name == "_update":
            self.emit("void nc_script_update(void)")
        else:
            self.emit("static int %s(%s)" % (
                name, ", ".join("int " + p for p in f["params"]) or "void"))
        self.emit("{")
        self.locals.append(set(f["params"]))
        for s in f["body"]:
            self.stmt(s, 1)
        # Only add a fallback return when the body can actually fall off the
        # end -- an unconditional one would be unreachable and warn.
        ends_in_return = bool(f["body"]) and f["body"][-1]["k"] == "return"
        if name not in ("_ready", "_update") and not ends_in_return:
            self.emit("return 0;", 1)
        self.locals.pop()
        self.emit("}")
        self.emit()

    def stmt(self, s, ind):
        k = s["k"]
        if k == "pass":
            self.emit(";", ind)
        elif k in ("break", "continue"):
            self.emit(k + ";", ind)
        elif k == "return":
            self.emit("return %s;" % (self.expr(s["expr"]) if s["expr"] else "0"),
                      ind)
        elif k == "local":
            self.locals[-1].add(s["name"])
            self.emit("int %s = %s;" % (s["name"], self.expr(s["expr"])), ind)
        elif k == "assign":
            self.check_name(s["name"], s["line"])
            self.emit("%s = %s;" % (s["name"], self.expr(s["expr"])), ind)
        elif k == "exprstmt":
            self.emit("%s;" % self.expr(s["expr"]), ind)
        elif k == "if":
            self.emit("if (%s) {" % self.expr(s["cond"]), ind)
            for b in s["body"]:
                self.stmt(b, ind + 1)
            if s["orelse"]:
                self.emit("} else {", ind)
                for b in s["orelse"]:
                    self.stmt(b, ind + 1)
            self.emit("}", ind)
        elif k == "while":
            self.emit("while (%s) {" % self.expr(s["cond"]), ind)
            for b in s["body"]:
                self.stmt(b, ind + 1)
            self.emit("}", ind)
        elif k == "for":
            var = s["var"]
            self.locals[-1].add(var)
            if s["end"] is None:
                lo, hi = "0", self.expr(s["start"])
            else:
                lo, hi = self.expr(s["start"]), self.expr(s["end"])
            self.emit("for (int %s = %s; %s < %s; %s++) {"
                      % (var, lo, var, hi, var), ind)
            for b in s["body"]:
                self.stmt(b, ind + 1)
            self.emit("}", ind)
        else:
            raise ScriptError(s.get("line", 0), f"cannot generate {k}")

    def check_name(self, name, line):
        if name in self.globals:
            return
        for scope in self.locals:
            if name in scope:
                return
        raise ScriptError(line, f"'{name}' is not defined. Declare it with "
                                f"'var {name} = 0' first.")

    def expr(self, e):
        k = e["k"]
        if k == "num":
            return str(e["v"])
        if k == "str":
            return e["v"]
        if k == "name":
            if e["v"] in self.api.CONSTANTS:
                return self.api.CONSTANTS[e["v"]]
            self.check_name(e["v"], e["line"])
            return e["v"]
        if k == "un":
            if e["op"] == "not":
                return "(!%s)" % self.expr(e["v"])
            return "(-%s)" % self.expr(e["v"])
        if k == "bin":
            op = {"and": "&&", "or": "||"}.get(e["op"], e["op"])
            return "(%s %s %s)" % (self.expr(e["l"]), op, self.expr(e["r"]))
        if k == "call":
            return self.call(e)
        raise ScriptError(e.get("line", 0), f"cannot generate expression {k}")

    def call(self, e):
        name = e["name"]
        args = [self.expr(a) for a in e["args"]]

        if name in self.api.FUNCTIONS:
            spec = self.api.FUNCTIONS[name]
            if spec["args"] is not None and len(args) != spec["args"]:
                raise ScriptError(e["line"],
                                  f"{name}() takes {spec['args']} argument(s), "
                                  f"got {len(args)}")
            return "%s(%s)" % (spec["c"], ", ".join(args))

        if name in self.user_funcs:
            want = self.user_funcs[name]
            if len(args) != want:
                raise ScriptError(e["line"],
                                  f"{name}() takes {want} argument(s), "
                                  f"got {len(args)}")
            return "%s(%s)" % (name, ", ".join(args))

        known = sorted(list(self.api.FUNCTIONS) + list(self.user_funcs))
        raise ScriptError(e["line"],
                          f"unknown function '{name}'. Available: "
                          + ", ".join(known))


# ---- entry point --------------------------------------------------------

def compile_source(src, source_name="script.ncs"):
    from . import ncscript_api as api
    tokens = tokenize(src)
    globals_, funcs = Parser(tokens, api).parse()
    return Generator(globals_, funcs, api, source_name).generate()


def compile_file(path, out_path):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    import os
    c = compile_source(src, os.path.basename(path))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(c)
    return len(c.splitlines())
