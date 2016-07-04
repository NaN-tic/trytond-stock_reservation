#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .stock import *
from .purchase import *

def register():
    Pool.register(
        Reservation,
        CreateReservationsStart,
        WaitReservationStart,
        PrintReservationGraphStart,
        Move,
        PurchaseLine,
        Production,
        Sale,
        ShipmentOut,
        ShipmentOutReturn,
        ShipmentIn,
        ShipmentInternal,
        Purchase,
        PurchaseRequest,
        module='stock_reservation', type_='model')
    Pool.register(
        CreateReservations,
        WaitReservation,
        PrintReservationGraph,
        module='stock_reservation', type_='wizard')
    Pool.register(
        ReservationGraph,
        module='stock_reservation', type_='report')
