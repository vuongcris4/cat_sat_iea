import time
from .models import OptimizationLog


def log_optimization(user, module, input_data, parameters, func, *args, **kwargs):
    """
    Wrapper to run an optimization function and log the result.
    
    Usage:
        result = log_optimization(
            user=request.user,
            module='cat_sat',
            input_data={'pieces': [...], 'stock_length': 6000},
            parameters={'blade_width': 2.5, 'max_surplus': 100},
            func=my_optimize_function,
            arg1, arg2, ...
        )
    """
    start_time = time.time()
    log_entry = OptimizationLog(
        user=user,
        module=module,
        input_data=input_data,
        parameters=parameters,
    )
    
    try:
        result = func(*args, **kwargs)
        duration = time.time() - start_time
        log_entry.duration_seconds = duration
        log_entry.status = 'success'
        # Extract summary from result if available
        if isinstance(result, dict):
            log_entry.output_summary = {
                k: v for k, v in result.items()
                if k in ('total_bars', 'total_waste_mm', 'waste_percentage', 'total_surplus')
            }
        log_entry.save()
        return result
    except Exception as e:
        duration = time.time() - start_time
        log_entry.duration_seconds = duration
        log_entry.status = 'error'
        log_entry.error_message = str(e)
        log_entry.save()
        raise
