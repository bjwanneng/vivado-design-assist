# Sample XDC with only input/output delays, no clock
set_input_delay -clock [get_clocks clk] 2.0 [get_ports data_in]
set_output_delay -clock [get_clocks clk] 1.5 [get_ports data_out]
set_false_path -from [get_ports reset_n]
set_false_path -from [get_ports test_mode]
set_false_path -from [get_ports scan_en]
set_false_path -from [get_ports jtag_tck]
