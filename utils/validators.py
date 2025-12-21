VALID_SIGNALS = {-1, 0, 1}

def validate_signal(signal):
    if signal not in VALID_SIGNALS:
        raise ValueError(f"Invalid signal: {signal}")
