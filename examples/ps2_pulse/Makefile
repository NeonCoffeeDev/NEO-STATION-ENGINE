# @NAME@ - Neon Coffee PS2 liveness test
EE_BIN  = game.elf
EE_OBJS = src/main.o
EE_LIBS = -ldraw -lgraph -lmath3d -lpacket -ldma

all: $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
