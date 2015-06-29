#:before:stock/stock:section:cancelar#

Reserva de stock
----------------
Como ya hemos comentado, cuando cambiamos el estado del albarán a *Reservado*,
el sistema realiza las reservas de stock teniendo en cuenta únicamente la
cantidad de stock que hay en el momento del cambio de estado. Por lo tanto, el
albarán que antes cambie de estado tendrá prioridad sobre los demás,
independientemente de la fecha de entrega del pedido o de las necesidades de
nuestra gestión. Para poder asignar una reserva de stock, a un albarán
priorizando su fecha de entrega, y evitar así que un determinado stock vaya a
parar a a una venta con menos prioridad de salida, tenemos el asistente *Crear
reservas de stock* al que accederemos por medio de |menu_reservation_wizard|.

Este asistente nos abrirá una ventana emergente donde deberemos indicar si
queremos crear las reservas de stock, y si queremos que estas se creen en
estado *En espera*. Si las creamos en estado *En espera* el stock quedará ya
reservado atendiendo a las necesidades del momento y no se asignará a ningún
otro  albarán o producción. Si no marcamos este campo, las reservas se
realizarán en estado *Borrador* por lo que podremos realizar cualquier
modificación sobre ellas antes de cambiar el estado a *En espera*. Hay que
tener en cuenta que una línea de reserva no hace efectiva la reserva hasta que
cambia a estado *En espera*. Además, en caso de volver a poner en marcha el
asistente, las líneas en estado *Borrador* serán recalculadas en caso de haber
nuevas necesidades de stock.

.. view:: stock_reservation.create_reservations_start_view_form

Una vez realizado el cálculo y creadas las líneas, estas serán clasificadas
según la naturaleza de la reserva en las diferentes pestañas que podremos
encontrar en la vista principal de las reservas de stock, accediendo por medio
de |menu_reservation|. En primer lugar el sistema buscará si el material a
reservar se encuentra en stock y, en caso de no tener stock del producto,
mirará si lo puede comprar o lo puede producir. Si el producto a reservar se
encuentra en stock, la linea de la reserva (ya esté en estado *En espera* o en
*Borrador*) nos aparecerá en la pestaña *En stock*. Si el sistema no encuentra
stock del producto a reservar, generará una solicitud de compra o producción
para poder satisfacer la reserva de stock y la línea de reserva se creará en
la pestaña *Asignado a tiempo* o *Asignado en retraso* dependiendo de la fecha
de entrega que tiene informada la venta. Esta línea quedará asociada a la
solicitud de compra o producción por medio del campo |origen|.

Por último, una vez se entregue la mercancía y se genere el albarán de salida
correspondiente, la línea o líneas de reserva de stock cambiarán su estado a
realizado. Si se produjera alguna devolución, o la compra o producción se tuvo
que hacer por más unidades de las que necesitábamos, estas unidades nos
aparecerán en la pestaña *Sobrante*.


.. |menu_reservation_wizard| tryref:: stock_reservation.menu_stock_reservation/complete_name
.. |menu_reservation| tryref:: stock_reservation.menu_stock_reservation_create/complete_name
.. |origen| field:: stock.reservation/source_document