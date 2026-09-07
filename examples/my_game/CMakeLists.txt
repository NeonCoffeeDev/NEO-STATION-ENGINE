# my_game - Neon Coffee PS1 project
#
# Do not run cmake directly; use `ncc build`. It picks a space-free build directory,
# which PSn00bSDK's post-link step requires. See docs/KNOWN-ISSUES.md.

cmake_minimum_required(VERSION 3.21)

project(
	my_game
	LANGUAGES   C ASM
	VERSION     0.1.0
	DESCRIPTION "Neon Coffee PS1 project"
)

file(GLOB _sources CONFIGURE_DEPENDS src/*.c)

psn00bsdk_add_executable(game GPREL ${_sources})
target_include_directories(game PRIVATE include)

# If the project has a scene.json, `ncc build` compiles it to scene.ncpkg before
# configuring, and it gets linked in as the `nc_package` symbol. Projects with
# geometry in C simply have no scene.json and skip this.
if(EXISTS "${PROJECT_SOURCE_DIR}/scene.ncpkg")
	psn00bsdk_target_incbin(game PRIVATE nc_package "${PROJECT_SOURCE_DIR}/scene.ncpkg")
endif()

psn00bsdk_add_cd_image(
	iso              # target name
	game             # -> game.bin + game.cue
	iso.xml
	DEPENDS game system.cnf
)
