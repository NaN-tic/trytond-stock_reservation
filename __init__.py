#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .stock import *


def register():
    Pool.register(
        Reservation,
        CreateReservationsStart,
        WaitReservationStart,
        Move,
        PurchaseLine,
        Production,
        Sale,
        ShipmentOut,
        Purchase,
        PurchaseRequest,
        module='stock_reservation', type_='model')
    Pool.register(
        CreateReservations,
        WaitReservation,
        module='stock_reservation', type_='wizard')
