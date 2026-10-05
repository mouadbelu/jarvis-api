READ_ONLY_TOOLS = {
    "time",
    "calculator",
    "web_search",
    "file_search",
}

ACTION_TOOLS = {
    "send_email",
    "delete_file",
    "purchase",
    "change_account_setting",
    "run_command",
}

def requires_confirmation(tool_name: str) -> bool:
    return tool_name in ACTION_TOOLS

def is_allowed(tool_name: str) -> bool:
    return tool_name in READ_ONLY_TOOLS or tool_name in ACTION_TOOLS
