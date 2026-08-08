"""Capa de consultas para los reportes del panel de administrador.

Todas las funciones son puras: reciben un `event` (o `None`) y devuelven
estructuras de datos planas, sin tocar `request`. Asi las consumen igual la
vista HTML, la exportacion CSV y los tests.

Convenciones del modulo:

- Las ordenes canceladas (`OrderStatus.CANCELLED`) se excluyen de todo calculo
  de ingreso y se reportan por separado.
- Los montos se devuelven como `Decimal` con dos decimales (ver `_money`).
- El margen es *estimado*: `SalesOrderItem` congela el precio de venta pero no
  el costo, asi que se usa el `StallProduct.cost_ucoin` vigente y se excluyen
  los items cuyo producto fue borrado (`stall_product` quedo en NULL).

Nota sobre agregaciones: `Stall` tiene una relacion multivaluada hacia
`SalesOrder` y esta a su vez hacia `SalesOrderItem`. Anotar sumas de ambas en
un mismo queryset multiplica los totales por el producto cartesiano de los
JOIN, asi que los agregados de orden y de linea se calculan en consultas
separadas y se fusionan en Python.
"""

from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Avg, Count, DecimalField, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate

from accounting.models import TopupChannel, TopupRecord, TopupStatus, WalletBalanceCache
from commerce.models import CartItem, OrderStatus, SalesOrder, SalesOrderItem
from events.models import EventMembership, ProfileType
from operations.models import StaffAuditLog, SupportTicket, SupportTicketStatus
from stalls.models import (
    ItemNature,
    MapSpot,
    MapSpotStatus,
    Stall,
    StallLocationAssignment,
    StallProduct,
    StallStatus,
    StallVendorMembership,
    StockMode,
)

ZERO = Decimal("0.00")

#: Estados que representan una orden pagada pero todavia no entregada.
PENDING_DELIVERY_STATUSES = (
    OrderStatus.PAID,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.PARTIALLY_DELIVERED,
)


def _money(amount):
    """Normaliza cualquier valor agregado a un Decimal monetario."""
    if amount is None:
        return ZERO
    return Decimal(amount).quantize(Decimal("0.01"))


def _ratio(part, whole):
    """Porcentaje 0-100 como float, tolerante a divisor cero."""
    if not whole:
        return 0.0
    return round(float(part) / float(whole) * 100, 1)


def _event_tzinfo(event):
    """Zona horaria del evento para cortar las series por dia local."""
    try:
        return ZoneInfo(event.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return None


def _paid_orders(event):
    """Ordenes que cuentan como ingreso del evento."""
    return SalesOrder.objects.filter(event=event).exclude(status=OrderStatus.CANCELLED)


def _paid_order_items(event):
    """Lineas de las ordenes que cuentan como ingreso del evento."""
    return SalesOrderItem.objects.filter(order__event=event).exclude(order__status=OrderStatus.CANCELLED)


def _decimal_sum(field):
    return Coalesce(Sum(field), ZERO, output_field=DecimalField(max_digits=14, decimal_places=2))


def _estimated_margin_by(event, group_field):
    """Margen estimado agrupado por `group_field`.

    Solo considera lineas con producto vigente, porque el costo se lee del
    catalogo actual y no de un snapshot en la orden.
    """
    margin_expr = ExpressionWrapper(
        (F("unit_price_snapshot") - F("stall_product__cost_ucoin")) * F("quantity"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    rows = (
        _paid_order_items(event)
        .filter(stall_product__isnull=False)
        .values(group_field)
        .annotate(margin=Coalesce(Sum(margin_expr), ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)))
    )
    return {row[group_field]: _money(row["margin"]) for row in rows}


# ---------------------------------------------------------------------------
# Ventas
# ---------------------------------------------------------------------------


def sales_kpis(*, event):
    """Indicadores globales de venta del evento."""
    empty = {
        "revenue": ZERO,
        "orders": 0,
        "average_ticket": ZERO,
        "units": 0,
        "buyers": 0,
        "cancelled_orders": 0,
        "cancelled_amount": ZERO,
        "margin": ZERO,
    }
    if not event:
        return empty

    paid = _paid_orders(event).aggregate(
        revenue=_decimal_sum("total_ucoin"),
        orders=Count("id"),
        buyers=Count("buyer_user_id", distinct=True),
    )
    units = _paid_order_items(event).aggregate(units=Coalesce(Sum("quantity"), 0))["units"]
    cancelled = SalesOrder.objects.filter(event=event, status=OrderStatus.CANCELLED).aggregate(
        orders=Count("id"),
        amount=_decimal_sum("total_ucoin"),
    )
    revenue = _money(paid["revenue"])
    orders = paid["orders"] or 0
    margin = sum(_estimated_margin_by(event, "order__stall_id").values(), ZERO)

    return {
        "revenue": revenue,
        "orders": orders,
        "average_ticket": _money(revenue / orders) if orders else ZERO,
        "units": units or 0,
        "buyers": paid["buyers"] or 0,
        "cancelled_orders": cancelled["orders"] or 0,
        "cancelled_amount": _money(cancelled["amount"]),
        "margin": _money(margin),
    }


def sales_by_stall(*, event):
    """Ranking de quioscos por ingreso: el reporte de "quien vendio mas".

    La venta se atribuye al quiosco (`SalesOrder.stall`), que es el unico
    vinculo directo del modelo. Los vendedores se listan como dato informativo
    del quiosco, no como atribucion: un quiosco admite hasta 3 vendedores y la
    orden no registra quien la despacho.
    """
    if not event:
        return []

    order_rows = {
        row["stall_id"]: row
        for row in (
            _paid_orders(event)
            .values("stall_id")
            .annotate(
                revenue=_decimal_sum("total_ucoin"),
                orders=Count("id"),
                buyers=Count("buyer_user_id", distinct=True),
            )
        )
    }
    unit_rows = {
        row["order__stall_id"]: row["units"]
        for row in (
            _paid_order_items(event).values("order__stall_id").annotate(units=Coalesce(Sum("quantity"), 0))
        )
    }
    cancelled_rows = {
        row["stall_id"]: row["cancelled"]
        for row in (
            SalesOrder.objects.filter(event=event, status=OrderStatus.CANCELLED)
            .values("stall_id")
            .annotate(cancelled=Count("id"))
        )
    }
    margin_rows = _estimated_margin_by(event, "order__stall_id")
    location_rows = {
        row.stall_id: row.spot.label
        for row in StallLocationAssignment.objects.select_related("spot").filter(event=event)
    }

    stalls = Stall.objects.filter(event=event).prefetch_related(
        "vendor_memberships__vendor_user",
    )
    total_revenue = sum((_money(row["revenue"]) for row in order_rows.values()), ZERO)

    rows = []
    for stall in stalls:
        aggregates = order_rows.get(stall.id, {})
        revenue = _money(aggregates.get("revenue"))
        orders = aggregates.get("orders", 0)
        vendors = [
            membership.vendor_user.get_username()
            for membership in stall.vendor_memberships.all()
        ]
        rows.append(
            {
                "stall_id": stall.id,
                "stall_code": stall.code,
                "stall_name": stall.name,
                "status_display": stall.get_status_display(),
                "spot_label": location_rows.get(stall.id, ""),
                "vendors": vendors,
                "vendors_display": ", ".join(vendors) or "Sin vendedor",
                "revenue": revenue,
                "orders": orders,
                "units": unit_rows.get(stall.id, 0),
                "buyers": aggregates.get("buyers", 0),
                "average_ticket": _money(revenue / orders) if orders else ZERO,
                "revenue_share": _ratio(revenue, total_revenue),
                "margin": margin_rows.get(stall.id, ZERO),
                "cancelled_orders": cancelled_rows.get(stall.id, 0),
            }
        )

    rows.sort(key=lambda row: (row["revenue"], row["orders"]), reverse=True)
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def sales_by_day(*, event):
    """Serie diaria de ingreso y ordenes, cortada en la zona horaria del evento."""
    if not event:
        return []

    rows = list(
        _paid_orders(event)
        .annotate(day=TruncDate("created_at", tzinfo=_event_tzinfo(event)))
        .values("day")
        .annotate(revenue=_decimal_sum("total_ucoin"), orders=Count("id"))
        .order_by("day")
    )
    peak = max((_money(row["revenue"]) for row in rows), default=ZERO)
    return [
        {
            "day": row["day"],
            "revenue": _money(row["revenue"]),
            "orders": row["orders"],
            "share_of_peak": _ratio(_money(row["revenue"]), peak),
        }
        for row in rows
    ]


def orders_by_status(*, event):
    """Conteo y monto de ordenes por estado, incluyendo estados sin ocurrencias."""
    if not event:
        return []

    totals = {
        row["status"]: row
        for row in (
            SalesOrder.objects.filter(event=event)
            .values("status")
            .annotate(orders=Count("id"), amount=_decimal_sum("total_ucoin"))
        )
    }
    return [
        {
            "status": status,
            "status_display": label,
            "orders": totals.get(status, {}).get("orders", 0),
            "amount": _money(totals.get(status, {}).get("amount")),
        }
        for status, label in OrderStatus.choices
    ]


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------


def top_products(*, event, limit=None):
    """Productos mas vendidos por unidades, con ingreso y margen estimado.

    Agrupa por el producto vigente cuando existe y, para lineas cuyo producto
    fue borrado, por el nombre congelado en la orden.
    """
    if not event:
        return []

    rows = list(
        _paid_order_items(event)
        .values("stall_product_id", "product_name_snapshot", "order__stall__name")
        .annotate(
            units=Coalesce(Sum("quantity"), 0),
            revenue=_decimal_sum("line_total_snapshot"),
            orders=Count("order_id", distinct=True),
        )
    )
    margin_rows = _estimated_margin_by(event, "stall_product_id")

    products = []
    for row in rows:
        units = row["units"] or 0
        revenue = _money(row["revenue"])
        products.append(
            {
                "stall_product_id": row["stall_product_id"],
                "product_name": row["product_name_snapshot"],
                "stall_name": row["order__stall__name"],
                "units": units,
                "revenue": revenue,
                "orders": row["orders"],
                "average_price": _money(revenue / units) if units else ZERO,
                "margin": margin_rows.get(row["stall_product_id"], ZERO),
                "is_deleted_product": row["stall_product_id"] is None,
            }
        )

    products.sort(key=lambda row: (row["units"], row["revenue"]), reverse=True)
    for position, row in enumerate(products, start=1):
        row["rank"] = position
    return products[:limit] if limit else products


def products_without_sales(*, event):
    """Productos activos del catalogo que no han vendido una sola unidad."""
    if not event:
        return []

    sold_ids = set(
        _paid_order_items(event)
        .filter(stall_product__isnull=False)
        .values_list("stall_product_id", flat=True)
        .distinct()
    )
    rows = (
        StallProduct.objects.select_related("stall", "category")
        .filter(event=event, is_active=True)
        .exclude(id__in=sold_ids)
        .order_by("stall__name", "display_name")
    )
    return [
        {
            "product_name": product.display_name,
            "stall_name": product.stall.name,
            "category": product.category.name if product.category else "Sin categoria",
            "price": _money(product.price_ucoin),
            "stock_qty": product.stock_qty,
            "item_nature_display": product.get_item_nature_display(),
        }
        for product in rows
    ]


def sales_by_category(*, event):
    """Unidades e ingreso agrupados por categoria y subcategoria del catalogo."""
    if not event:
        return []

    rows = list(
        _paid_order_items(event)
        .filter(stall_product__isnull=False)
        .values("stall_product__category__name", "stall_product__subcategory__name")
        .annotate(units=Coalesce(Sum("quantity"), 0), revenue=_decimal_sum("line_total_snapshot"))
    )
    total_revenue = sum((_money(row["revenue"]) for row in rows), ZERO)
    result = [
        {
            "category": row["stall_product__category__name"] or "Sin categoria",
            "subcategory": row["stall_product__subcategory__name"] or "Sin subcategoria",
            "units": row["units"] or 0,
            "revenue": _money(row["revenue"]),
            "revenue_share": _ratio(_money(row["revenue"]), total_revenue),
        }
        for row in rows
    ]
    result.sort(key=lambda row: row["revenue"], reverse=True)
    return result


def low_stock_products(*, event):
    """Productos inventariables por debajo de su umbral de bajo inventario.

    Mismo criterio que aplica `StallProduct.is_low_stock`, resuelto en SQL para
    poder contarlo y listarlo sin cargar todo el catalogo.
    """
    if not event:
        return []

    rows = (
        StallProduct.objects.select_related("stall")
        .filter(
            event=event,
            is_active=True,
            is_sold_out_manual=False,
            item_nature=ItemNature.INVENTORIABLE,
            stock_mode=StockMode.FINITE,
            low_stock_threshold__isnull=False,
            stock_qty__gt=0,
            stock_qty__lte=F("low_stock_threshold"),
        )
        .order_by("stock_qty", "stall__name", "display_name")
    )
    return [
        {
            "product_name": product.display_name,
            "stall_name": product.stall.name,
            "stock_qty": product.stock_qty,
            "low_stock_threshold": product.low_stock_threshold,
            "stock_base_qty": product.stock_base_qty,
            "sold_share": _ratio(
                (product.stock_base_qty or 0) - (product.stock_qty or 0),
                product.stock_base_qty or 0,
            ),
        }
        for product in rows
    ]


def sold_out_products(*, event):
    """Productos activos agotados, por inventario en cero o marca manual."""
    if not event:
        return []

    rows = (
        StallProduct.objects.select_related("stall")
        .filter(event=event, is_active=True)
        .filter(
            Q(is_sold_out_manual=True)
            | Q(item_nature=ItemNature.INVENTORIABLE, stock_mode=StockMode.FINITE, stock_qty=0)
        )
        .order_by("stall__name", "display_name")
    )
    return [
        {
            "product_name": product.display_name,
            "stall_name": product.stall.name,
            "reason": "Marcado como agotado" if product.is_sold_out_manual else "Inventario en cero",
            "stock_base_qty": product.stock_base_qty,
        }
        for product in rows
    ]


def product_kpis(*, event):
    """Resumen de catalogo e inventario."""
    if not event:
        return {
            "active_products": 0,
            "sold_products": 0,
            "unsold_products": 0,
            "low_stock": 0,
            "sold_out": 0,
        }

    active_products = StallProduct.objects.filter(event=event, is_active=True).count()
    sold_products = (
        _paid_order_items(event)
        .filter(stall_product__isnull=False)
        .values("stall_product_id")
        .distinct()
        .count()
    )
    return {
        "active_products": active_products,
        "sold_products": sold_products,
        "unsold_products": len(products_without_sales(event=event)),
        "low_stock": len(low_stock_products(event=event)),
        "sold_out": len(sold_out_products(event=event)),
    }


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


def top_buyers(*, event, limit=None):
    """Clientes por gasto acumulado en el evento."""
    if not event:
        return []

    rows = list(
        _paid_orders(event)
        .values("buyer_user_id", "buyer_user__username", "buyer_user__email")
        .annotate(spent=_decimal_sum("total_ucoin"), orders=Count("id"))
    )
    profiles = {
        membership.user_id: membership.get_profile_type_display()
        for membership in EventMembership.objects.filter(event=event)
    }
    units = {
        row["order__buyer_user_id"]: row["units"]
        for row in _paid_order_items(event)
        .values("order__buyer_user_id")
        .annotate(units=Coalesce(Sum("quantity"), 0))
    }

    buyers = []
    for row in rows:
        spent = _money(row["spent"])
        orders = row["orders"] or 0
        buyers.append(
            {
                "user_id": row["buyer_user_id"],
                "username": row["buyer_user__username"],
                "email": row["buyer_user__email"] or "",
                "profile_type": profiles.get(row["buyer_user_id"], "Sin membresia"),
                "spent": spent,
                "orders": orders,
                "units": units.get(row["buyer_user_id"], 0),
                "average_ticket": _money(spent / orders) if orders else ZERO,
            }
        )

    buyers.sort(key=lambda row: (row["spent"], row["orders"]), reverse=True)
    for position, row in enumerate(buyers, start=1):
        row["rank"] = position
    return buyers[:limit] if limit else buyers


def topup_summary(*, event):
    """Recargas exitosas por canal y ranking de staff que otorgo efectivo."""
    empty = {
        "total_amount": ZERO,
        "total_count": 0,
        "average_amount": ZERO,
        "by_channel": [],
        "by_staff": [],
        "failed_count": 0,
        "pending_count": 0,
    }
    if not event:
        return empty

    successful = TopupRecord.objects.filter(event=event, status=TopupStatus.SUCCESS)
    totals = successful.aggregate(amount=_decimal_sum("amount_ucoin"), count=Count("id"))
    total_amount = _money(totals["amount"])
    total_count = totals["count"] or 0

    channel_rows = {
        row["channel"]: row
        for row in successful.values("channel").annotate(
            amount=_decimal_sum("amount_ucoin"),
            count=Count("id"),
        )
    }
    by_channel = [
        {
            "channel": channel,
            "channel_display": label,
            "amount": _money(channel_rows.get(channel, {}).get("amount")),
            "count": channel_rows.get(channel, {}).get("count", 0),
            "amount_share": _ratio(_money(channel_rows.get(channel, {}).get("amount")), total_amount),
        }
        for channel, label in TopupChannel.choices
    ]

    by_staff = [
        {
            "username": row["staff_user__username"],
            "amount": _money(row["amount"]),
            "count": row["count"],
        }
        for row in (
            successful.filter(staff_user__isnull=False)
            .values("staff_user__username")
            .annotate(amount=_decimal_sum("amount_ucoin"), count=Count("id"))
            .order_by("-amount")
        )
    ]

    status_counts = dict(
        TopupRecord.objects.filter(event=event)
        .values_list("status")
        .annotate(total=Count("id"))
    )
    return {
        "total_amount": total_amount,
        "total_count": total_count,
        "average_amount": _money(total_amount / total_count) if total_count else ZERO,
        "by_channel": by_channel,
        "by_staff": by_staff,
        "failed_count": status_counts.get(TopupStatus.FAILED, 0),
        "pending_count": status_counts.get(TopupStatus.PENDING, 0),
    }


def wallet_summary(*, event):
    """Control contable: recargado, gastado y saldo remanente.

    `unreconciled` expone la diferencia entre el saldo esperado
    (recargado - gastado) y el saldo cacheado en `WalletBalanceCache`. Deberia
    ser cero; un valor distinto senala ajustes manuales o descuadre.
    """
    empty = {
        "topped_up": ZERO,
        "spent": ZERO,
        "outstanding": ZERO,
        "expected_outstanding": ZERO,
        "unreconciled": ZERO,
        "wallets_with_balance": 0,
        "redemption_rate": 0.0,
    }
    if not event:
        return empty

    topped_up = _money(
        TopupRecord.objects.filter(event=event, status=TopupStatus.SUCCESS).aggregate(
            amount=_decimal_sum("amount_ucoin")
        )["amount"]
    )
    spent = _money(_paid_orders(event).aggregate(amount=_decimal_sum("total_ucoin"))["amount"])
    outstanding = _money(
        WalletBalanceCache.objects.filter(event=event).aggregate(amount=_decimal_sum("balance_ucoin"))["amount"]
    )
    expected = _money(topped_up - spent)
    return {
        "topped_up": topped_up,
        "spent": spent,
        "outstanding": outstanding,
        "expected_outstanding": expected,
        "unreconciled": _money(outstanding - expected),
        "wallets_with_balance": WalletBalanceCache.objects.filter(event=event, balance_ucoin__gt=0).count(),
        "redemption_rate": _ratio(spent, topped_up),
    }


def audience_summary(*, event):
    """Membresias vs. compradores efectivos, con desglose por tipo de perfil."""
    empty = {"members": 0, "buyers": 0, "conversion_rate": 0.0, "by_profile": []}
    if not event:
        return empty

    members = EventMembership.objects.filter(event=event).count()
    buyer_ids = set(_paid_orders(event).values_list("buyer_user_id", flat=True).distinct())

    profile_members = dict(
        EventMembership.objects.filter(event=event)
        .values_list("profile_type")
        .annotate(total=Count("id"))
    )
    profile_buyers = dict(
        EventMembership.objects.filter(event=event, user_id__in=buyer_ids)
        .values_list("profile_type")
        .annotate(total=Count("id"))
    )
    by_profile = [
        {
            "profile_type": profile,
            "profile_display": label,
            "members": profile_members.get(profile, 0),
            "buyers": profile_buyers.get(profile, 0),
            "conversion_rate": _ratio(profile_buyers.get(profile, 0), profile_members.get(profile, 0)),
        }
        for profile, label in ProfileType.choices
    ]
    return {
        "members": members,
        "buyers": len(buyer_ids),
        "conversion_rate": _ratio(len(buyer_ids), members),
        "by_profile": by_profile,
    }


# ---------------------------------------------------------------------------
# Operacion
# ---------------------------------------------------------------------------


def fulfillment_summary(*, event):
    """Estado de entregas y tiempo promedio desde la compra hasta la entrega."""
    empty = {
        "pending": 0,
        "pending_amount": ZERO,
        "delivered": 0,
        "partially_delivered": 0,
        "cancelled": 0,
        "average_delivery_minutes": None,
        "delivery_rate": 0.0,
    }
    if not event:
        return empty

    orders = SalesOrder.objects.filter(event=event)
    pending = orders.filter(status__in=PENDING_DELIVERY_STATUSES).aggregate(
        count=Count("id"),
        amount=_decimal_sum("total_ucoin"),
    )
    delivered = orders.filter(status=OrderStatus.DELIVERED).count()
    paid_total = _paid_orders(event).count()

    duration = ExpressionWrapper(F("delivered_at") - F("created_at"), output_field=DurationField())
    average_delta = (
        orders.filter(delivered_at__isnull=False).aggregate(average=Avg(duration))["average"]
    )
    return {
        "pending": pending["count"] or 0,
        "pending_amount": _money(pending["amount"]),
        "delivered": delivered,
        "partially_delivered": orders.filter(status=OrderStatus.PARTIALLY_DELIVERED).count(),
        "cancelled": orders.filter(status=OrderStatus.CANCELLED).count(),
        "average_delivery_minutes": (
            round(average_delta.total_seconds() / 60, 1) if average_delta else None
        ),
        "delivery_rate": _ratio(delivered, paid_total),
    }


def support_summary(*, event):
    """Tickets de soporte por tipo y por estado, con los abiertos mas antiguos."""
    empty = {"total": 0, "open": 0, "by_type": [], "by_status": [], "oldest_open": []}
    if not event:
        return empty

    tickets = SupportTicket.objects.filter(event=event)
    open_statuses = (SupportTicketStatus.OPEN, SupportTicketStatus.IN_PROGRESS)
    return {
        "total": tickets.count(),
        "open": tickets.filter(status__in=open_statuses).count(),
        "by_type": [
            {"label": row["ticket_type"], "total": row["total"]}
            for row in tickets.values("ticket_type").annotate(total=Count("id")).order_by("-total")
        ],
        "by_status": [
            {"label": row["status"], "total": row["total"]}
            for row in tickets.values("status").annotate(total=Count("id")).order_by("-total")
        ],
        "oldest_open": [
            {
                "summary": ticket.summary,
                "username": ticket.user.get_username(),
                "status_display": ticket.get_status_display(),
                "created_at": ticket.created_at,
            }
            for ticket in tickets.select_related("user")
            .filter(status__in=open_statuses)
            .order_by("created_at")[:10]
        ],
    }


def staff_activity(*, event):
    """Acciones registradas en la bitacora, agrupadas por tipo y por usuario."""
    empty = {"total": 0, "by_action": [], "by_staff": []}
    if not event:
        return empty

    logs = StaffAuditLog.objects.filter(event=event)
    return {
        "total": logs.count(),
        "by_action": [
            {"label": row["action_type"], "total": row["total"]}
            for row in logs.values("action_type").annotate(total=Count("id")).order_by("-total")
        ],
        "by_staff": [
            {"label": row["staff_user__username"], "total": row["total"]}
            for row in logs.values("staff_user__username").annotate(total=Count("id")).order_by("-total")
        ],
    }


def operations_snapshot(*, event):
    """Ocupacion del mapa, estado de quioscos y carritos sin cerrar."""
    empty = {
        "spots_total": 0,
        "spots_by_status": [],
        "stalls_total": 0,
        "stalls_by_status": [],
        "assigned_stalls": 0,
        "vendors_assigned": 0,
        "active_carts": 0,
        "active_cart_value": ZERO,
    }
    if not event:
        return empty

    spot_counts = dict(MapSpot.objects.filter(event=event).values_list("status").annotate(total=Count("id")))
    stall_counts = dict(Stall.objects.filter(event=event).values_list("status").annotate(total=Count("id")))

    cart_value = ExpressionWrapper(
        F("quantity") * F("stall_product__price_ucoin"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    carts = CartItem.objects.filter(event=event).aggregate(
        users=Count("user_id", distinct=True),
        value=Coalesce(Sum(cart_value), ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
    )
    return {
        "spots_total": sum(spot_counts.values()),
        "spots_by_status": [
            {"label": label, "total": spot_counts.get(status, 0)} for status, label in MapSpotStatus.choices
        ],
        "stalls_total": sum(stall_counts.values()),
        "stalls_by_status": [
            {"label": label, "total": stall_counts.get(status, 0)} for status, label in StallStatus.choices
        ],
        "assigned_stalls": StallLocationAssignment.objects.filter(event=event).count(),
        "vendors_assigned": StallVendorMembership.objects.filter(event=event).count(),
        "active_carts": carts["users"] or 0,
        "active_cart_value": _money(carts["value"]),
    }
