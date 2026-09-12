# NC Bench -- the cost model, measured rather than guessed.
#
# Deliberately not an ncc project: it needs no VN, no audio, no materials and
# no asset pipeline, and keeping it plain means it builds and boots even when
# the engine around it does not.

EE_BIN  = bench.elf
EE_OBJS = src/main.o src/font_data.o
EE_LIBS = -ldraw -lgraph -lpacket -ldma -lm

all: $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
