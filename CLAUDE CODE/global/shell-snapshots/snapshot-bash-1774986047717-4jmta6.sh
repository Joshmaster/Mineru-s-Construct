# Snapshot file
# Unset all aliases to avoid conflicts with functions
unalias -a 2>/dev/null || true
shopt -s expand_aliases
# Check for rg availability
if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then
  function rg {
  if [[ -n $ZSH_VERSION ]]; then
    ARGV0=rg 'C:\Users\OWNER\.local\bin\claude.exe' "$@"
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=rg 'C:\Users\OWNER\.local\bin\claude.exe' "$@"
  elif [[ $BASHPID != $$ ]]; then
    exec -a rg 'C:\Users\OWNER\.local\bin\claude.exe' "$@"
  else
    (exec -a rg 'C:\Users\OWNER\.local\bin\claude.exe' "$@")
  fi
}
fi
export PATH=$PATH
