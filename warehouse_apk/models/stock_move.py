# -*- coding: utf-8 -*-
##############################################################################
#    License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
#    Copyright (C) 2019 Comunitea Servicios Tecnológicos S.L. All Rights Reserved
#    Vicente Ángel Gutiérrez <vicente@comunitea.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, models, fields
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

BINARYPOSITION = {'product_id': 0, 'location_id': 1, 'lot_id': 2, 'package_id': 3, 'location_dest_id': 4, 'result_package_id': 5, 'qty_done': 6}
FLAG_PROP = {'view': 1, 'req': 2, 'done': 4};


class StockMove(models.Model):
    _inherit = 'stock.move'

    order = 'picking_id, sequence, id'


    @api.multi
    def _compute_move_lines_count(self):
        for sm in self:
            sm.move_lines_count = len(sm.move_line_ids)

    tracking = fields.Selection(related='product_id.tracking')
    wh_code = fields.Char(related='product_id.wh_code')
    sale_id = fields.Many2one(related='picking_id.sale_id')
    move_lines_count = fields.Integer("# Moves", compute="_compute_move_lines_count")
    field_status_apk = fields.Char(compute='compute_field_status')
    field_status = fields.Boolean(compute="compute_field_status")
    default_location = fields.Selection(related='picking_type_id.group_code.default_location')
    barcode_re = fields.Char(related='picking_type_id.warehouse_id.barcode_re')
    product_re = fields.Char(related='picking_type_id.warehouse_id.product_re')
    removal_priority = fields.Integer(compute='compute_move_order', store=True)
    active_location_id = fields.Many2one('stock.location', copy=False)
    picking_field_status = fields.Boolean(related = 'picking_id.field_status')
    move_line_location_id = fields.Many2one('stock.location', compute="compute_move_line_location_id")
    wh_location = fields.Char(related="move_line_location_id.name")
    apk_filter_by_qty = fields.Char(compute="compute_move_line_location_id")
    apk_order = fields.Integer(string="Apk order", default=0)
    batch_id = fields.Many2one(related='picking_id.batch_id')
    total_qty_done = fields.Integer(related="batch_id.total_qty_done")

    @api.multi
    def compute_move_line_location_id(self):
        for sm in self:
            if sm.quantity_done < sm.reserved_availability:
                sm.apk_filter_by_qty = 'Pendientes'
            elif sm.quantity_done >= sm.reserved_availability:
                sm.apk_filter_by_qty = 'Hechos'

            if sm.move_line_ids:
                if sm.default_location:
                    loc_ids = sm.mapped('move_line_ids').mapped(sm.default_location)
                    sm.move_line_location_id = loc_ids[:1]

    @api.multi
    @api.depends('move_line_ids.location_id', 'move_line_ids.location_dest_id')
    def compute_move_order(self):
        for move in self:
            field = move.default_location
            sml = move.move_line_ids
            if sml:
                move.removal_priority = min([x.removal_priority for x in sml.mapped(field)])
            else:
                move.removal_priority = 999999

    # @api.depends('move_line_ids.field_status')
    # def compute_field_status(self):
    #     for move in self:
    #         move.field_status = all(x.field_status for x in move.move_line_ids)

    def action_show_details(self):
        res = super().action_show_details()
        res['context']['default_field_status_apk'] = self.get_default_field_status()
        res['context']['show_lots_m2o'] = self.has_tracking != 'none'
        return res

    @api.multi
    def compute_field_status(self):
        for sm in self:
            field_status_apk = sm.get_default_field_status()
            sm.field_status = all(x.field_status_rdone() for x in sm.move_line_ids)
            for campo in BINARYPOSITION.keys():
                campo_state = all(line.read_status(campo, 'req') and line.read_status(campo, 'done') for line in sm.move_line_ids)
                if campo_state:
                    field_status_apk = self._write_status(field_status_apk, campo, 'done', campo_state)
            sm.field_status_apk = field_status_apk

    def _read_status_(self, status_field, campo, propiedad):
        pos = BINARYPOSITION[campo]
        field = int(status_field[pos:pos+1])
        return field and FLAG_PROP(propiedad)

    def write_field_position(self, status_field, campo, value):
        pos = BINARYPOSITION[campo]
        return '{}{}{}'.format(status_field[:pos], value, status_field[pos+1:])

    def _write_status(self, field_status_apk, campo, propiedad, value=True):
        pos = BINARYPOSITION[campo]
        field = int(field_status_apk[pos:pos + 1])
        actual = field & FLAG_PROP[propiedad]
        if value and not actual:
            field += FLAG_PROP[propiedad]
        elif not value and actual:
            field -= FLAG_PROP[propiedad]
        return '{}{}{}'.format(field_status_apk[:pos], field, field_status_apk[pos+1:])

    def write_status_(self, status_field, campo, propiedad):
        pos = BINARYPOSITION[campo]
        field = int(status_field[pos:pos+1])
        return field and not FLAG_PROP(propiedad)

    def get_default_field_status(self):
        val = self.picking_type_id.group_code.field_status_apk or '1111111'
        if self.tracking == 'none':
            val = self._write_status(val, 'lot_id', 'view', False)
            val = self._write_status(val, 'lot_id', 'req', False)
        return val

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super(StockMove, self)._prepare_move_line_vals(
            quantity=quantity, reserved_quant=reserved_quant)
        vals['field_status_apk'] = self.get_default_field_status()
        return vals


    def find_model_object(self, domain=[], search_str='', ids=[]):
        product_domain = domain
        if ids:
            product_domain += [('id', 'in', ids)]
        product_domain += ['|', ('product_id.barcode', '=', search_str), ('product_id.wh_code', '=', search_str)]
        res = self.search_read(product_domain, ['id', 'apk_name'], order ='apk_order')
        if res:
            return [x['id'] for x in res]
            ## Busco en los lotes:
        lot_domain = [('move_id', 'in', ids), ('lot_id.name', '=', search_str)]
        res = self.env['stock.move.line'].search_read(lot_domain, ['move_id'])
        if res:
            return [x['move_id'][0] for x in res]
        location_domain = ['|', ('location_id.barcode', '=', search_str), ('location_dest_id.barcode', '=', search_str)]
        res = self.env['stock.move.line'].search_read(location_domain, ['move_id'])
        if res:
            return [x['move_id'][0] for x in res]
        return False

    def get_default_location(self):
        if self.active_location_id:
            return self.active_location_id.get_model_object()[0]
        elif self.move_line_ids:
            return self.move_line_ids[0][self['default_location']].get_model_object()[0]
        else:
            return self[self['default_location']].get_model_object()[0]

    @api.model
    def get_relative_move_info(self, values):
        move_id = values.get('move_id', 0)
        filter = values.get('filter_moves', 'Pendientes')
        inc = values.get('inc', 0)
        move_id = self.browse(move_id)
        apk_order = move_id.apk_order
        batch_id = move_id.picking_id.batch_id
        move_domain = batch_id.get_move_domain_for_picking(filter, batch_id, inc=inc, limit=1, apk_order=apk_order)
        new_move = self.search(move_domain)
        if not new_move:
            apk_order = -1
            move_domain = batch_id.get_move_domain_for_picking(filter, batch_id, inc=inc, limit=1, apk_order=apk_order)
            new_move = self.search(move_domain)

        if not new_move or new_move.id == move_id.id:
            return move_id.id
        print ("Busco movimiento para {} y encuentro {}".format(move_id, new_move.id))
        return new_move.get_model_object(values)

    def get_model_object(self, values={}):

        values.update(order='apk_order asc')
        res = super().get_model_object(values=values)
        if values.get('view', 'tree') == 'tree':
            return res
        move_id = self
        if not move_id:
            domain = values.get('domain', [])
            limit = values.get('limit', 1)
            move_id = self.search(domain, limit, order="apk_order")
            if not move_id or len(move_id) != 1:
                return res
        res['product_id']['image'] = move_id.product_id.image_medium
        values.update(view='form', model='stock.move.line')
        domain = [('move_id', '=', move_id.id)]
        filter = values.get('filter_move_lines', 'Todos')
        if filter == 'Pendientes':
            domain += [('field_status', '=', False)]
        elif filter == 'Realizados':
            domain += [('field_status', '=', True)]

        limit = 10# values.get('sml_limit', 15)
        offset = 0# values.get('sml_offset', 0)
        sml_ids = self.env['stock.move.line'].search(
            domain,
            limit=limit,
            offset=offset,
            order= 'lot_id, write_date asc')

        if sml_ids:
            res['move_line_ids'] = sml_ids.sorted(lambda r: r.lot_id).get_model_object()
        else:
            res['move_line_ids'] = []

        res['active_location_id'] = self.get_default_location()
        return res

    def return_fields(self, view='tree'):
        fields = ['id', 'product_id', 'product_uom_qty', 'reserved_availability', 'quantity_done', 'tracking', 'state',
                   'move_lines_count', 'field_status', 'wh_code', 'move_line_location_id', 'total_qty_done',
                  'location_id', 'location_dest_id']
        if view == 'form':
            fields += ['apk_order','batch_id', 'picking_id', 'barcode_re', 'default_location', 'picking_field_status', 'field_status_apk', 'sale_id' , 'product_uom', 'active_location_id', 'move_lines_count']
        return fields

    @api.model
    def force_set_qty_done_apk(self, vals):
        move = self.browse(vals.get('id', False))
        if not move:
            return {'err': True, 'error': "No se ha encontrado el movimiento."}
        for move_line in move.move_line_ids:
            move_line.qty_done = move_line.product_uom_qty
        if not move.picking_type_id.allow_overprocess and move.quantity_done > move.reserved_availability:
            raise ValidationError("No puedes procesar más cantidad de lo reservado para el movimiento")
        return True

    def compute_active_location_id(self, field_location, move):
        move = move or self
        domain = [('id', '=', move[field_location].id), ('putaway_strategy_id.product_id', '=', move.product_id.id)]
        loc_id = self.env['stock.location'].seach(domain, limit=1) or move[field_location]
        return loc_id

        #
        # putaway_id = self[field_location].putaway_strategy_id
        # if putaway_id:
        #     domain = [('putaway_id', '=', putaway_id), ('product_id', '=', self.product_id.id)]
        #     strat_id =  self.env['stock.fixed.putaway.strat'].search(domain)
        #     if strat_id:
        #         return strat_id.location_id
        # return self[field_location]

    @api.model
    def create_new_sml_id(self, values):
        if self:
            move_id = self
        else:
            move_id = values['id']
            move_id = self.env['stock.move'].browse(move_id)
        if not move_id:
            return False
        location = move_id.active_location_id or move_id[move_id.default_location] or self.env['stock.location']
        location_field = move_id.default_location

        move_vals = move_id._prepare_move_line_vals()
        sml_id = self.env['stock.move.line']
        if location != move_id[location_field]:
            move_vals[location_field] = move_id.active_location_id.id
            move_vals['field_status_apk'] = sml_id._write_status(move_vals['field_status_apk'], location_field, 'done')
        move_vals['qty_done'] = max(move_id.product_uom_qty - move_id.quantity_done, 0)
        new_sml_id = sml_id.create(move_vals)
        move_id._recompute_state()
        if self:
            values = {'id': move_id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': values.get('filter_move_lines', 'Todos')}
            return move_id.get_model_object(values)
        return new_sml_id

    @api.model
    def delete_move_line(self, vals):
        sml_id = vals.get('sml_id', False)
        sml_id = self.env['stock.move.line'].browse(sml_id)
        move_id = sml_id.move_id
        qty = sml_id.qty_done
        sml_id.unlink()
        move_id._update_reserved_quantity(qty, qty, move_id.location_id, lot_id=False, strict=False)
        move_id._recompute_state()
        values = {'id': move_id.id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': vals.get('filter_move_lines', 'Todos')}
        if not move_id.picking_type_id.allow_overprocess and move_id.quantity_done > move_id.product_uom_qty:
            raise ValidationError("No puedes procesar más cantidad de lo reservado para el movimiento")
        return self.env['info.apk'].get_apk_object(values)


    @api.model
    def create_move_lots(self, vals):

        move_id = vals.get('id', False)
        lot_names = vals.get('lot_names', False)
        move = self.browse(move_id)
        active_location_id = vals.get('active_location', False)
        if not move_id or not lot_names:
            return False

        ## Los moviemintos que no tengan lotes, le añado los que tengo, si no llegan añado nuevo. No borro ningún movimiento.
        ## Podría utilizar el lot_name pero me parece más limpio así, se crean y se añaden a los stock_move_line pq sino tendríamos
        ## distinta lógica según el tipo de albarán


        ## Actulizazo como hechos los movimientos que tengan lote en la lista y los quito para no crearlos
        if not active_location_id:
            active_location = move.active_location_id or move.move_line_location_id
            active_location_id = active_location.id
        sml_with_lot_ids = move.move_line_ids.filtered(lambda x: x.lot_id.name in lot_names)

        for sml_id in sml_with_lot_ids:
            sml_id.write_status('lot_id', 'done')
            #sml_id[move.default_location] = active_location_id
            if move.active_location_id:
                sml_id.write_status(move.default_location, 'done')
            if move.tracking == 'serial':
                sml_id.write_status('qty_done', 'done')
                sml_id.write_status(move['default_location'], 'done')
                sml_id.qty_done = 1
            lot_names.pop(lot_names.index(sml_id.lot_id.name))

        ##Si aún quedan lotes
        if lot_names:
            ## encuentro o creo los lotes que falten
            lot_ids = self.env['stock.production.lot']
            for lot in lot_names:
                lot_id = lot_ids.find_or_create_lot(lot, move.product_id, not move.picking_type_id.use_existing_lots)
                if lot_id:
                    lot_ids |= lot_id
            ##filtro todos los movimientos que no tengan lote y se lo añado
            sml_ids = move.move_line_ids.filtered(lambda x: not x.lot_id or not x.read_status('lot_id', 'done'))
            for sml in sml_ids:
                ## Por cada movimiento quito el primero, genero nueva reserva forzando el lote
                if not lot_ids:
                    break
                if move.location_id.should_bypass_reservation()\
                    or move.product_id.type == 'consu':
                    sml.lot_id = lot_ids[0]
                    lot_ids -= lot_ids[0]
                    new_move = sml
                else:
                    sml.unlink()
                    reserved = move._update_reserved_quantity(1, 1, move.location_id, lot_id=lot_ids[0], strict=False)

                    if not reserved:
                        ## buscon el move line con ese lote
                        ocup_dom = [('move_id.picking_type_id', '=', move.picking_type_id.id),
                                    ('product_id', '=', move.product_id.id),
                                    ('state', 'in', ('assigned', 'partially_available')),
                                    ('lot_id', '=', lot_ids[0].id)]
                        ocup_move_line = self.env['stock.move.line'].search(ocup_dom)
                        if ocup_move_line:
                            move_to_update = ocup_move_line.move_id
                            ocup_move_line.unlink()
                            reserved = move._update_reserved_quantity(1, 1, move.location_id, lot_id=lot_ids[0], strict=False)
                            if move_to_update._update_reserved_quantity(1, 1, move.location_id, strict=False) == 1:
                                move_to_update.write({'state': 'assigned'})
                    if not reserved:
                        raise ValidationError('No se ha podido reservar el lote {}'.format(lot_ids[0]))
                    move.write({'state': 'assigned'})
                    lot_ids -= lot_ids[0]
                    new_move = move.move_line_ids[-1]

                new_move.write_status('lot_id', 'done')
                new_move.qty_done = 1
                new_move.write_status('qty_done', 'done')
                #new_move[move.default_location] = active_location_id
                if move.active_location_id or active_location_id and move.tracking == 'serial':
                    new_move.write_status(move.default_location, 'done')
            ## Si quedan lotes, tengo que crear un movieminto por cada lote
            if lot_ids:
                for lot_id in lot_ids:
                    if move.quantity_done >= move.reserved_availability:
                        break
                    reserved = move._update_reserved_quantity(1, 1, move.location_id, lot_id=lot_id, strict=False)
                    if reserved:
                        new_move = move.move_line_ids[-1]
                        new_move.write_status('lot_id', 'done')
                        new_move.qty_done = 1
                        new_move.write_status('qty_done', 'done')
                        new_move[move.default_location] = active_location_id
                        if move.active_location_id:
                            new_move.write_status(move.default_location, 'done')
        move._recompute_state()
        ## Devuelvo la información del moviemitno para ahorrar una llamada desde la apk
        values = {'id': move.id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': vals.get('filter_move_lines', 'Todos')}
        if not move.picking_type_id.allow_overprocess and move.quantity_done > move.reserved_availability:
            raise ValidationError("No puedes procesar más cantidad de lo reservado para el movimiento")
        return self.env['info.apk'].get_apk_object(values)

    @api.model
    def load_eans(self, values):
        move_id = values.get('move_id', False)
        if not move_id:
            raise ValidationError("No hay un movimiento padre para estos números")
        location_id = values.get('location_id', False)
        if not location_id:
            raise ValidationError("No hay una ubicación definida")
        ean_ids = values.get('ean_ids', '')
        vals = []
        if ean_ids:
            ean_ids = values.get('ean_ids').split()
        else:
            ean_ids = []
        values.pop('ean_ids')
        if not ean_ids:
            raise ValidationError ("No hay ningún número de serie")
        move = self.browse(move_id)
        if move.quantity_done >= move.reserved_availability:
            raise ValidationError ("No puedes hacer más cantidad que lo que tienes reservado")

        vals = {'lot_names': ean_ids,
             'active_location_id': location_id,
             'id': move_id}
        return self.create_move_lots(vals)

    @api.model
    def move_assign_apk(self, values):

        move = self.browse(values.get('id'))
        if move:
            move._action_assign()
        values = {'id': move.id, 'model': 'stock.move', 'view': 'form'}
        return self.env['info.apk'].get_apk_object(values)

    @api.model
    def move_unreserve_apk(self, values):
        move = self.browse(values.get('id'))
        if move:
            move._do_unreserve()
        values = {'id': move.id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': values.get('filter_move_lines', 'Todos')}
        return self.env['info.apk'].get_apk_object(values)

    @api.model
    def clean_lots(self, values):
        move = self.browse(values.get('id'))
        if move:
            move.move_line_ids.write({'lot_name': '', 'lot_id': False, 'qty_done': 0})
        values = {'id': move.id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': values.get('filter_move_lines', 'Todos')}
        return self.env['info.apk'].get_apk_object(values)

    @api.model
    def set_qty_done_from_apk(self, vals):
        move_id = vals.get('move_id', False)
        quantity_done = vals.get('quantity_done', False)
        inc = vals.get('inc', False)
        filter = vals.get('filter_moves', 'Todos')
        if not move_id or not (quantity_done or inc):
            return {'err': True, 'error': "No se ha enviado la línea o la cantidad a modificar."}
        move = self.browse(move_id)
        if not move:
            return {'err': True, 'error': "La línea introducida no existe."}

        if inc:
            move.quantity_done += inc
        else:
            move.quantity_done = quantity_done
        if move:
            move._recompute_state()
            if not move.picking_type_id.allow_overprocess and move.quantity_done > move.reserved_availability:
                raise ValidationError("No puedes procesar más cantidad de lo reservado para el movimiento")
            return move.get_model_object()
        return False

    @api.model
    def assign_location_id(self, values):

        move = self.browse(values.get('id'))
        location_field = values.get('location_field')
        if location_field == move.default_location:
            return False
        location_id = values.get('location_id')
        ## Filtro los move_lines por los que no tenga el move.default_location
        smls = move.move_lines.filtered(lambda x: not x.read_status(move.default_location, 'done'))
        for move in smls:
            move.write_status(move.default_location, 'done')
        smls.write({move.default_location: location_id})
        values = {'id': move.id, 'model': 'stock.move', 'view': 'form', 'filter_move_lines': values.get('filter_move_lines', 'Todos')}
        return self.env['info.apk'].get_apk_object(values)

    @api.model
    def get_move_info_apk(self, vals):
        move_id = vals.get('id', False)
        index = vals.get('index', 0)
        if index:
            picking_id = self.search_read([('id', '=', move_id)], ['picking_id'])
            if not picking_id:
                return False
        if not move_id:
            return False
        move = self.browse(move_id)
        move_lines = move.picking_id.move_lines
        if index != 0:
            if index == -1:
                move_lines = reversed(move_lines)
            is_index = False
            for new_move in move_lines:
                if is_index:
                    break
                is_index = new_move == move
            if is_index:
                move = new_move
        product_id = move.product_id.with_context(location=move.location_id.id)
        data = {'id': move.id,
                'display_name': product_id.display_name,
                'state': move.state,
                'image': product_id.image_medium,
                'barcode': product_id.barcode,
                'picking_id': {'id': move.picking_id.id,
                                'display_name': move.picking_id.display_name,
                                'code': move.picking_id.picking_type_code},
                'tracking': product_id.tracking,
                'default_code': product_id.default_code,
                'qty_available': product_id.qty_available,
                'location_id': {'id': move.location_id.id,
                                'display_name': move.location_id.display_name,
                                'barcode': move.location_id.barcode},
                'location_dest_id': {'id': move.location_dest_id.id,
                                     'display_name': move.location_dest_id.display_name,
                                     'barcode': move.location_dest_id.barcode},
                'product_uom_qty': move.product_uom_qty,
                'uom_move': {'uom_id': move.product_uom.id, 'name': move.product_uom.name},
                'quantity_done': move.quantity_done,
                'ready_to_validate': sum(line.qty_done for line in move.picking_id.move_line_ids) == sum(line.product_uom_qty for line in move.picking_id.move_line_ids)
                }
        lot_id = []
        lot_ids = move.move_line_ids.mapped("lot_id")
        lot_names = move.move_line_ids.mapped("lot_name")
        for lot in lot_ids:
            lot_id.append({
                'id': lot.id,
                'name': lot.name
            })
        for lot_name in lot_names:
            lot_id.append({
                'id': False,
                'name': lot_name
            })
        data['lot_ids'] = lot_id
        return data