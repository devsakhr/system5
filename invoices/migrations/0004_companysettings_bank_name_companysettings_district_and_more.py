from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0003_companysettings_building_number_customer_postal_code_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='companysettings',
            name='bank_account_number',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='رقم الحساب البنكي'),
        ),
        migrations.AddField(
            model_name='companysettings',
            name='bank_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='اسم البنك'),
        ),
        migrations.AddField(
            model_name='companysettings',
            name='district',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='الحي'),
        ),
        migrations.AddField(
            model_name='companysettings',
            name='iban',
            field=models.CharField(blank=True, max_length=34, null=True, verbose_name='رقم الآيبان'),
        ),
        migrations.AddField(
            model_name='companysettings',
            name='invoice_seller_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='اسم البائع في الفاتورة'),
        ),
        migrations.AddField(
            model_name='companysettings',
            name='region',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='المنطقة'),
        ),
    ]
