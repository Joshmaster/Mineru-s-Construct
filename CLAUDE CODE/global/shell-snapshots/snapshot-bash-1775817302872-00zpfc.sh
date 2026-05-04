# Snapshot file
# Unset all aliases to avoid conflicts with functions
unalias -a 2>/dev/null || true
shopt -s expand_aliases
# Check for rg availability
if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then
  function rg {
  local _cc_bin="${CLAUDE_CODE_EXECPATH:-}"
  [[ -x $_cc_bin ]] || _cc_bin=$(command -v claude 2>/dev/null)
  if [[ ! -x $_cc_bin ]]; then command rg "$@"; return; fi
  if [[ -n $ZSH_VERSION ]]; then
    ARGV0=rg "$_cc_bin" "$@"
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=rg "$_cc_bin" "$@"
  elif [[ $BASHPID != $$ ]]; then
    exec -a rg "$_cc_bin" "$@"
  else
    (exec -a rg "$_cc_bin" "$@")
  fi
}
fi
export PATH=/c/Users/OWNER/bin:/mingw64/bin:/usr/local/bin:/usr/bin:/bin:/mingw64/bin:/usr/bin:/c/Users/OWNER/bin:/c/WINDOWS/system32:/c/WINDOWS:/c/WINDOWS/System32/Wbem:/c/WINDOWS/System32/WindowsPowerShell/v1.0:/c/WINDOWS/System32/OpenSSH:/cmd:/c/Sysinternals:/c/WINDOWS/system32:/c/WINDOWS:/c/WINDOWS/System32/Wbem:/c/WINDOWS/System32/WindowsPowerShell/v1.0:/c/WINDOWS/System32/OpenSSH:/c/Users/OWNER/AppData/Local/Programs/Python/Python312/Scripts:/c/Users/OWNER/AppData/Local/Programs/Python/Python312:/c/Users/OWNER/AppData/Local/Programs/Python/Launcher:/c/Users/OWNER/AppData/Local/Microsoft/WindowsApps:/c/Users/OWNER/AppData/Local/Programs/Tesseract-OCR:/c/Users/OWNER/.local/bin:/c/Users/OWNER/AppData/Local/Programs/Ollama:/c/Users/OWNER/.claude/bin:/c/Users/OWNER/AppData/Local/Microsoft/WinGet/Packages/SST.opencode_Microsoft.Winget.Source_8wekyb3d8bbwe:/usr/bin/vendor_perl:/usr/bin/core_perl
