idf_component_register()

# Do not generate flash file when building bootloader or is in early expansion of the build
if(SELFUPDATE_BUILD)
    return()
endif()
