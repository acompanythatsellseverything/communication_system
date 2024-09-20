from django.contrib import admin
from sms.models import OutgoingSMS, IncomingSMS, CallRecord

admin.site.register(OutgoingSMS)
admin.site.register(IncomingSMS)
admin.site.register(CallRecord)
