# Este módulo ya no define modelos propios.
# Todos los modelos fueron migrados al esquema v2:
#   - UserProfile   → events.EventMembership
#   - Wallet        → accounting.WalletBalanceCache
#   - WalletLedger  → accounting.LedgerEntry
#   - Recharge      → accounting.TopupRecord
#   - RechargeIssue → operations.SupportTicket
#   - FoodItem      → stalls.CatalogProduct
#   - CartItem      → commerce.CartItem
#   - Purchase      → commerce.SalesOrder
#   - PurchaseItem  → commerce.SalesOrderItem
