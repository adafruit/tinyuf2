set(lcd_srcs "lcd.c")

idf_component_register(SRCS "${lcd_srcs}"
                       INCLUDE_DIRS "include"
                       REQUIRES boards src)
