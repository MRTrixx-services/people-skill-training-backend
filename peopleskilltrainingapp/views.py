# # peopleskilltrainingapp/views.py
# from django.views.generic import View
# from django.http import FileResponse
# import os
# from django.conf import settings

# class FrontendAppView(View):
#     def get(self, request, *args, **kwargs):
#         # Correct path to your frontend build
#         index_file = os.path.join(settings.BASE_DIR, 'build', 'index.html')
#         return FileResponse(open(index_file, 'rb'))
