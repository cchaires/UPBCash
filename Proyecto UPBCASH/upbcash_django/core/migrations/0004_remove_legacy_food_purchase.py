from django.db import migrations


class Migration(migrations.Migration):
    """
    Elimina los modelos legacy de comida y compras del esquema v1.
    Fueron reemplazados por stalls.CatalogProduct/StallProduct y commerce.SalesOrder/SalesOrderItem.
    """

    dependencies = [
        ("core", "0003_walletledger"),
    ]

    operations = [
        migrations.DeleteModel(name="CartItem"),
        migrations.DeleteModel(name="FoodItem"),
        migrations.DeleteModel(name="PurchaseItem"),
        migrations.DeleteModel(name="Purchase"),
    ]
