# Generated by Django 2.2.8 on 2019-12-05 04:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profile_page', '0012_remove_profile_payment_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='payment_plan',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Free'),
                                                            (2, 'Standard'),
                                                            (3, 'Enterprise')], default=1),
        ),
        migrations.AddField(
            model_name='profile',
            name='unlimited_customer',
            field=models.BooleanField(default=False),
        ),
    ]
