from django.db import migrations, models


def update_balance_trigger_column(apps, schema_editor):
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

            SELECT COALESCE(SUM(amount_ucoin_signed), 0)
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


def revert_balance_trigger_column(apps, schema_editor):
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


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0003_ledger_balance_trigger"),
    ]

    operations = [
        migrations.RenameField(
            model_name="ledgerentry",
            old_name="amount_mxn_signed",
            new_name="amount_ucoin_signed",
        ),
        # RenameField no reescribe la expresion Q() dentro del CheckConstraint historico
        # (sigue referenciando el nombre viejo del campo) - se recrea explicitamente para
        # que el estado de la migracion coincida con el nuevo nombre. Mismo `name=`, no
        # genera un DROP/ADD real de otro constraint distinto.
        migrations.RemoveConstraint(
            model_name="ledgerentry",
            name="check_ledger_entry_nonzero_amount",
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(amount_ucoin_signed=0),
                name="check_ledger_entry_nonzero_amount",
            ),
        ),
        migrations.RunPython(update_balance_trigger_column, reverse_code=revert_balance_trigger_column),
    ]
