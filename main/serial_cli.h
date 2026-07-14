#pragma once

void serial_cli_init(void);
void serial_cli_register_cmd(const char *name, const char *help,
                             void (*handler)(int argc, char **argv));
