# hello_cube - Neon Coffee PS1 project
#
# Do not run cmake directly; use `ncc build`. It picks a space-free build directory,
# which PSn00bSDK's post-link step requires. See docs/KNOWN-ISSUES.md.

cmake_minimum_required(VERSION 3.21)

project(
	hello_cube
	LANGUAGES   C ASM
	VERSION     0.1.0
	DESCRIPTION "Neon Coffee PS1 project"
)

file(GLOB _sources CONFIGURE_DEPENDS src/*.c)

psn00bsdk_add_executable(game GPREL ${_sources})
target_include_directories(game PRIVATE include)

psn00bsdk_add_cd_image(
	iso              # target name
	game             # -> game.bin + game.cue
	iso.xml
	DEPENDS game system.cnf
)
