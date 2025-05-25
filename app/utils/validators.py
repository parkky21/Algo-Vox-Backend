from fastapi import HTTPException
import codecs

def validate_custom_function(function_code: str):
    try:
        # Decode any escaped characters (e.g., \n) into real newlines
        decoded_code = codecs.decode(function_code, "unicode_escape")

        local_vars = {}
        print(decoded_code)
        exec(decoded_code, {}, local_vars)

        fn_ref = local_vars.get("tool_fn")
        if not fn_ref:
            raise ValueError("Function 'tool_fn' not defined.")
        if not callable(fn_ref):
            raise ValueError("'tool_fn' is not callable.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid custom function: {str(e)}")
