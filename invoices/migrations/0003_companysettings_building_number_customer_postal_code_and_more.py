from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0002_alter_invoiceitem_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='companysettings',
            name='building_number',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='رقم المبنى'),
        ),
        migrations.AddField(
            model_name='customer',
            name='building_number',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='رقم المبنى'),
        ),
        migrations.AddField(
            model_name='customer',
            name='postal_code',
            field=models.CharField(blank=True, max_length=9, null=True, verbose_name='الرمز البريدي'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='building_number',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='رقم المبنى'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='postal_code',
            field=models.CharField(blank=True, max_length=9, null=True, verbose_name='الرمز البريدي'),
        ),
    ]
