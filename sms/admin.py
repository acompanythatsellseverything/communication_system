from django.contrib import admin

from sms.models import OutgoingSMS, IncomingSMS

admin.site.register(OutgoingSMS)
admin.site.register(IncomingSMS)
