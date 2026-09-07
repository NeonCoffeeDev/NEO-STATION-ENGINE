# @NAME@ - Neon Coffee PS2 texture test
#
# Do not run make directly; use `ncc build`.

EE_BIN  = game.elf
EE_OBJS = src/main.o src/logo_data.o

EE_LIBS = -ldraw -lgraph -lmath3d -lpacket -ldma

all: $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
