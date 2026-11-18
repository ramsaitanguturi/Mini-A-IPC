savedcmd_aipc_module.mod := printf '%s\n'   aipc_module.o | awk '!x[$$0]++ { print("./"$$0) }' > aipc_module.mod
