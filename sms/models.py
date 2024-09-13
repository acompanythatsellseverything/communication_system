import requests
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save
from time import sleep
from pathlib import Path


class OutgoingSMS(models.Model):
    phone = models.CharField(max_length=36, db_index=True)
    created_date = models.DateTimeField(auto_now_add=True)
    text = models.TextField()


class IncomingSMS(models.Model):
    phone = models.CharField(max_length=36, db_index=True)
    created_date = models.DateTimeField(auto_now_add=True)
    text = models.TextField()


class CallRecord(models.Model):
    pbx_call_id = models.CharField(max_length=56, db_index=True)
    call_id_with_rec = models.CharField(max_length=56, db_index=True, blank=True, null=True)
    caller_id = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    caller_phone = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    client_number = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    operator_number = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    call_start_time = models.DateTimeField(blank=True, null=True)
    call_end_time = models.DateTimeField(blank=True, null=True)
    destination_number = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    call_type = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    duration = models.IntegerField(blank=True, null=True)
    status_code = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    is_recorder = models.BooleanField(default=False)
    disposition = models.CharField(max_length=36, db_index=True, blank=True, null=True)
    caller_record_link = models.URLField(blank=True, null=True)
    events = models.TextField(blank=True, null=True, default="")

    def __str__(self):
        return self.pbx_call_id


@receiver(post_save, sender=CallRecord)
def download_call_signal(sender, instance, *args, **kwargs):
    if "NOTIFY_RECORD" in instance.events:
        path = Path(f"./data/{instance.pbx_call_id}.mp3")
        if not path.is_file():
            sleep(12)
            record = requests.get(instance.caller_record_link)
            with open(path, "wb") as f:
                f.write(record.content)
