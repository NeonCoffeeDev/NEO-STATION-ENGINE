.section .data.nc_package, "aw"
.balign 4

.global nc_package
.type nc_package, @object
.size nc_package, (nc_package_end - nc_package)
nc_package:
	.incbin "C:/Users/bates/Desktop/NC-HOMEBREW/examples/my_game/scene.ncpkg"

.local nc_package_end
nc_package_end:

.balign 4

.section .data.nc_package_size, "aw"
.balign 4

.global nc_package_size
.type nc_package_size, @object
.size nc_package_size, 4
nc_package_size:
	.int (nc_package_end - nc_package)
