from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import OptimizationLog


@login_required
def history_view(request):
    """Page to view optimization history."""
    logs = OptimizationLog.objects.select_related('user').all()[:100]
    
    # Filters
    module = request.GET.get('module')
    if module:
        logs = logs.filter(module=module)
    
    status = request.GET.get('status')
    if status:
        logs = logs.filter(status=status)
    
    return render(request, 'optimization_logs/history.html', {'logs': logs})


@login_required
def history_api(request):
    """JSON API for optimization history."""
    logs = OptimizationLog.objects.select_related('user').all()[:50]
    data = [{
        'id': log.id,
        'user': log.user.username if log.user else 'N/A',
        'module': log.get_module_display(),
        'created_at': log.created_at.isoformat(),
        'duration': f"{log.duration_seconds:.1f}s" if log.duration_seconds else '-',
        'status': log.status,
        'input_pieces': len(log.input_data.get('pieces', [])),
        'output_summary': log.output_summary,
    } for log in logs]
    return JsonResponse({'logs': data})
