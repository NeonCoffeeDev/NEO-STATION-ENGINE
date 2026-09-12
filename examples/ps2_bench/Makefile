# NC Bench and the GIF dump.
#
# Deliberately not ncc projects: they need no VN, no audio, no materials and
# no asset pipeline, and keeping them plain means they build and boot even
# when the engine around them does not.

EE_BIN  = bench.elf
EE_OBJS = src/main.o src/font_data.o
EE_BIN2 = gifdump.elf
EE_OBJS2 = src/gifdump.o src/font_data.o
EE_LIBS = -ldraw -lgraph -lpacket -ldma -lm

all: $(EE_BIN) $(EE_BIN2)

$(EE_BIN2): $(EE_OBJS2)
	$(EE_CC) -T$(PS2SDK)/ee/startup/linkfile $(EE_OPTFLAGS) -o $(EE_BIN2) $(EE_OBJS2) $(EE_LDFLAGS) $(EE_LIBS)

clean:
	rm -f $(EE_BIN) $(EE_OBJS) $(EE_BIN2) $(EE_OBJS2)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
