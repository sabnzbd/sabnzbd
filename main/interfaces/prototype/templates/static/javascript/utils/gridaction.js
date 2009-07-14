//-------------------------------------------------------------------------------------------------------------
//                                                       GRIDACTION
//-------------------------------------------------------------------------------------------------------------
        // vim: ts=4:sw=4:nu:fdc=2:nospell
        /**
        * RowAction plugin for Ext grid
        *
        * Contains renderer for an icon and fires events when icon is clicked
        *
        * @author    Ing. Jozef Sakalos <jsakalos at aariadne dot com>
        * @date      December 29, 2007
        * @version    Ext.ux.grid.RowAction.js 126 2008-01-31 03:33:50Z jozo 
        *
        * @license Ext.ux.grid.RowAction is licensed under the terms of
        * the Open Source LGPL 3.0 license.  Commercial use is permitted to the extent
        * that the code/component(s) do NOT become part of another Open Source or Commercially
        * licensed development library or toolkit without explicit permission.
        * 
        * License details: http://www.gnu.org/licenses/lgpl.html
        */

        Ext.ns('Ext.ux.grid');

        /**
        * @class Ext.ux.grid.RowAction
        * @extends Ext.util.Observable
        *
        * Creates new RowAction plugin
        * @constructor
        * @param {Object} config The config object
        *
        * @cfg {String} iconCls css class that defines background image
        */
        Ext.ux.grid.RowAction = function(config) {
        Ext.apply(this, config);

        this.addEvents({
            /**
             * @event beforeaction
             * Fires before action event. Return false to cancel the subsequent action event.
             * @param {Ext.grid.GridPanel} grid
             * @param {Ext.data.Record} record Record corresponding to row clicked
             * @param {Integer} rowIndex 
             */
             beforeaction:true
            /**
             * @event action
             * Fires when icon is clicked
             * @param {Ext.grid.GridPanel} grid
             * @param {Ext.data.Record} record Record corresponding to row clicked
             * @param {Integer} rowIndex 
             */
            ,action:true
        });

        Ext.ux.grid.RowAction.superclass.constructor.call(this);
        };

        Ext.extend(Ext.ux.grid.RowAction, Ext.util.Observable, {
         header:''
        ,sortable:false
        ,dataIndex:''
        ,width:20
        ,fixed:true
        ,lazyRender:true
        ,iconCls:''

        // private - plugin initialization
        ,init:function(grid) {
            this.grid = grid;
            var view = grid.getView();
            grid.on({
                render:{scope:this, fn:function() {
                    view.mainBody.on({
                        click:{scope:this, fn:this.onClick}
                    });
                }}
            });
            if(!this.renderer) {
                this.renderer = function(value, cell, record, row, col, store) {
                    cell.css += (cell.css ? ' ' : '') + 'ux-grid3-row-action-cell';
                    //very very bad work-around for changing resume/pause icon
                    var customClass = this.getIconCls(record, row, col);
                    if (customClass == "icon-pause" && record.data.status == "Paused") customClass = 'icon-play';
                    else if (customClass == "icon-play" && record.data.status != "Paused") customClass = 'icon-pause';
                    var retval = '<div class="' + customClass + '"';
                    retval += this.style ? ' style="' + this.style + '"' : '';
                    retval += this.qtip ? ' ext:qtip="' + this.qtip +'"' : '';
                    retval += '> </div>';
                    return retval;
                }.createDelegate(this);
            }
        } // eo function init

        // override for custom processing
        ,getIconCls:function(record, row, col) {
            return this.boundIndex ? record.get(this.boundIndex) : this.iconCls;
        } // eo function getIconCls
        
        // override for custom processing
        ,setIconCls:function(cls) {
            this.iconCls = cls;
        } // eo function getIconCls

        // private - icon click handler
        ,onClick:function(e, target) {
            var record, iconCls;
            var row = e.getTarget('.x-grid3-row');
            var col = this.grid.getView().getCellIndex(e.getTarget('.ux-grid3-row-action-cell'));

            if(false !== row && false !== col) {
                record = this.grid.store.getAt(row.rowIndex);
                iconCls = this.getIconCls(record, row.rowIndex, col);
                //very very bad work-around for changing resume/pause icon
                if (iconCls == 'icon-pause' && record.data.status == "Paused") iconCls = 'icon-play';              
                if(Ext.fly(target).hasClass(iconCls)) {
                    if(false !== this.fireEvent('beforeaction', this.grid, record, row.rowIndex)) {
                        this.fireEvent('action', this.grid, record, row.rowIndex, e);
                    }
                }
            }
        } // eo function onClick
        });

        // eof  