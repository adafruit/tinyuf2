set(MCU_VARIANT MIMXRT1011)

target_sources(${TARGET} PUBLIC
  ${CMAKE_CURRENT_LIST_DIR}/clock_config.c
  ${CMAKE_CURRENT_LIST_DIR}/flash_config.c
  )

target_compile_definitions(${TARGET} PUBLIC
  CPU_MIMXRT1011DAE5A
  )
