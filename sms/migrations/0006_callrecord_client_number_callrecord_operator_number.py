# Generated by Django 5.1 on 2024-09-12 14:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sms', '0005_incomingsms_created_date_outgoingsms_created_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='callrecord',
            name='client_number',
            field=models.CharField(blank=True, db_index=True, max_length=36, null=True),
        ),
        migrations.AddField(
            model_name='callrecord',
            name='operator_number',
            field=models.CharField(blank=True, db_index=True, max_length=36, null=True),
        ),
    ]
