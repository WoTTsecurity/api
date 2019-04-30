from django.db import migrations


def copy_profiles(apps, schema_editor):
    Profile1 = apps.get_model('profile_page', 'Profile')
    Profile2 = apps.get_model('device_registry', 'Profile')
    for profile in Profile1.objects.all():
        company_name = profile.company_name if profile.company_name is not None else ''
        Profile2.objects.create(user=profile.user, company_name=company_name)


class Migration(migrations.Migration):
    dependencies = [
        ('device_registry', '0019_profile'),
    ]

    operations = [
        migrations.RunPython(copy_profiles),
    ]
