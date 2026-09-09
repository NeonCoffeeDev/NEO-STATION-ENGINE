# @NAME@ - Neon Coffee PlayStation 2 project
#
# Do not run make directly; use `ncc build`. It sets PS2DEV, PS2SDK and GSKIT
# and puts the toolchain on PATH, which is most of what a PS2 build needs.
#
# PS2SDK builds with Makefiles rather than CMake, which is why the PS1 and PS2
# sides of this engine do not share a build system. Trying to force one would
# mean reimplementing PS2SDK's link rules, and those are the part most likely to
# be subtly wrong.

EE_BIN  = game.elf
EE_OBJS = src/main.o src/nc_materials.o

# libdraw and libgraph are the GS drawing and display libraries; libpacket and
# libdma build and send the GIF packets the GPU actually reads.
EE_LIBS = -ldraw -lgraph -lmath3d -lpacket -ldma -lpad -lm

all: $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal

src/main.o: src/nc_events.h src/nc_room_layout.h
