# Generated by Django 5.0 on 2024-02-23 14:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0007_alter_product_view'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='view',
            field=models.IntegerField(default=127),
        ),
    ]
