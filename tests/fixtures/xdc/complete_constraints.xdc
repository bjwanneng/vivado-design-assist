# Sample XDC with complete constraints
create_clock -period 4.000 -name clk_sys [get_ports clk]
create_clock -period 8.000 -name clk_ext [get_ports clk_ext_in]

set_clock_groups -asynchronous \
  -group [get_clocks clk_sys] \
  -group [get_clocks clk_ext]

set_input_delay -clock [get_clocks clk_sys] -max 2.0 [get_ports data_in]
set_input_delay -clock [get_clocks clk_sys] -min 0.5 [get_ports data_in]
set_output_delay -clock [get_clocks clk_sys] -max 1.5 [get_ports data_out]
set_output_delay -clock [get_clocks clk_sys] -min 0.3 [get_ports data_out]

set_clock_uncertainty 0.1 [get_clocks clk_sys]
set_clock_uncertainty 0.15 [get_clocks clk_ext]
