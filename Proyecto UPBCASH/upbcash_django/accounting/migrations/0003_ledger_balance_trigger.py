from django.db import migrations


def create_balance_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION accounting_validate_ledger_transaction_balance()
        RETURNS trigger AS $$
        DECLARE
            target_tx uuid;
            balance numeric(14,2);
        BEGIN
            target_tx := COALESCE(NEW.transaction_id, OLD.transaction_id);
            IF target_tx IS NULL THEN
                RETURN NULL;
            END IF;

            SELECT COALESCE(SUM(amount_mxn_signed), 0)
            INTO balance
            FROM accounting_ledgerentry
            WHERE transaction_id = target_tx;

            IF balance <> 0 THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'Ledger transaction '
                        || target_tx::text
                        || ' is not balanced. delta='
                        || balance::text;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    schema_editor.execute("DROP TRIGGER IF EXISTS trg_accounting_ledger_balance ON accounting_ledgerentry;")
    schema_editor.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_accounting_ledger_balance
        AFTER INSERT OR UPDATE OR DELETE ON accounting_ledgerentry
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION accounting_validate_ledger_transaction_balance();
        """
    )


def drop_balance_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS trg_accounting_ledger_balance ON accounting_ledgerentry;")
    schema_editor.execute("DROP FUNCTION IF EXISTS accounting_validate_ledger_transaction_balance();")


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(create_balance_trigger, reverse_code=drop_balance_trigger),
    ]
