from django.shortcuts import render

def index(request):
    return render(request, 'cat_laser/index.html')
