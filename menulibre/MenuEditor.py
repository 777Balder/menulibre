# -*- coding: utf-8 -*-
#   Alacarte Menu Editor - Simple fd.o Compliant Menu Editor
#   Copyright (C) 2006  Travis Watkins, Heinrich Wendel
#
#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Library General Public
#   License as published by the Free Software Foundation; either
#   version 2 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Library General Public License for more details.
#
#   You should have received a copy of the GNU Library General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import locale
import os
import xml.dom.minidom
import xml.parsers.expat
from locale import gettext as _
from xml.sax.saxutils import escape

from gi.repository import GdkPixbuf, Gio, GLib, GMenu, Gtk

from . import util
from .enums import MenuItemTypes

locale.textdomain('menulibre')

icon_theme = Gtk.IconTheme.get_default()


def get_default_menu():
    """Return the filename of the default application menu."""
    prefix = os.environ.get('XDG_MENU_PREFIX', '')
    return prefix + 'applications.menu'


def on_icon_theme_changed(icon_theme, treestore):
    """Update the displayed icons when the icon theme changes."""
    for row in treestore:
        row[4] = load_icon(row[3], 48)


def load_fallback_icon(icon_size):
    """If icon loading fails, load a fallback icon instead."""
    info = icon_theme.lookup_icon(
        "image-missing", icon_size,
        Gtk.IconLookupFlags.GENERIC_FALLBACK | Gtk.IconLookupFlags.USE_BUILTIN)
    return info.load_icon()


def load_icon(gicon, icon_size):
    """Load an icon, either from the icon theme or from a filename."""
    pixbuf = None

    if gicon is None:
        return None

    else:
        info = icon_theme.lookup_by_gicon(gicon, icon_size, 0)

        if info is None:
            pixbuf = load_fallback_icon(icon_size)
        else:
            try:
                pixbuf = info.load_icon()
            except GLib.GError:
                pixbuf = load_fallback_icon(icon_size)

    if pixbuf.get_width() != icon_size or pixbuf.get_height() != icon_size:
        pixbuf = pixbuf.scale_simple(
            icon_size, icon_size, GdkPixbuf.InterpType.HYPER)
    return pixbuf


def menu_to_treestore(treestore, parent, menu_items):
    """Convert the Alacarte menu to a standard treestore."""
    for item in menu_items:
        item_type = item[0]
        if item_type == MenuItemTypes.SEPARATOR:
            displayed_name = "--------------------"
            tooltip = _("Separator")
            filename = None
            icon = None
        else:
            displayed_name = escape(item[2]['display_name'])
            if not item[2]['show']:
                displayed_name = "<small><i>%s</i></small>" % displayed_name
            tooltip = item[2]['comment']
            icon = item[2]['icon']
            filename = item[2]['filename']
            icon_name = item[2]['icon_name']

        treeiter = treestore.append(
            parent, [displayed_name, tooltip, item_type,
            icon, icon_name, filename])

        if item_type == MenuItemTypes.DIRECTORY:
            treestore = menu_to_treestore(treestore, treeiter, item[3])

    return treestore


def get_treestore():
    """Get the TreeStore implementation of the current menu."""
    # Name, Comment, MenuItemType, GIcon (TreeView), icon-name, Filename
    treestore = Gtk.TreeStore(str, str, int, Gio.Icon, str, str)
    icon_theme.connect("changed", on_icon_theme_changed, treestore)
    menu = get_menus()[0]
    return menu_to_treestore(treestore, None, menu)


def get_submenus(menu, tree_dir):
    """Get the submenus for a tree directory."""
    structure = []
    for child in menu.getContents(tree_dir):
        if isinstance(child, GMenu.TreeSeparator):
            structure.append([MenuItemTypes.SEPARATOR, child, None, None])
        else:
            if isinstance(child, GMenu.TreeEntry):
                item_type = MenuItemTypes.APPLICATION
                entry_id = child.get_desktop_file_id()
                app_info = child.get_app_info()
                icon = app_info.get_icon()
                icon_name = "application-default-icon"
                display_name = app_info.get_display_name()
                generic_name = app_info.get_generic_name()
                comment = app_info.get_description()
                keywords = app_info.get_keywords()
                executable = app_info.get_executable()
                filename = child.get_desktop_file_path()
                hidden = app_info.get_is_hidden()
                submenus = None

            elif isinstance(child, GMenu.TreeDirectory):
                item_type = MenuItemTypes.DIRECTORY
                entry_id = child.get_menu_id()
                icon = child.get_icon()
                icon_name = "application-default-icon"
                display_name = child.get_name()
                generic_name = child.get_generic_name()
                comment = child.get_comment()
                keywords = []
                executable = None
                filename = child.get_desktop_file_path()
                hidden = False
                submenus = get_submenus(menu, child)

            if isinstance(icon, Gio.ThemedIcon):
                icon_name = icon.get_names()[0]
            elif isinstance(icon, Gio.FileIcon):
                icon_name = icon.get_file().get_path()

            details = {'display_name': display_name,
                       'generic_name': generic_name,
                       'comment': comment,
                       'keywords': keywords,
                       'executable': executable,
                       'filename': filename,
                       'icon': icon,
                       'icon_name': icon_name,
                       'show': not hidden}
            entry = [item_type, entry_id, details, submenus]
            structure.append(entry)

    return structure


def get_menus():
    """Get the menus from the MenuEditor"""
    menu = MenuEditor()
    structure = []
    toplevels = []
    for child in menu.getMenus(None):
        toplevels.append(child)
    for top in toplevels:
        structure.append(get_submenus(menu, top[0]))
    return structure


class MenuEditor(object):
    """MenuEditor"""

    def __init__(self, basename=None):
        """init"""
        basename = basename or get_default_menu()

        self.tree = GMenu.Tree.new(basename,
                                    GMenu.TreeFlags.SHOW_EMPTY |
                                    GMenu.TreeFlags.INCLUDE_EXCLUDED |
                                    GMenu.TreeFlags.INCLUDE_NODISPLAY |
                                    GMenu.TreeFlags.SHOW_ALL_SEPARATORS |
                                    GMenu.TreeFlags.SORT_DISPLAY_NAME)
        self.load()

        self.path = os.path.join(
            util.getUserMenuPath(), self.tree.props.menu_basename)
        self.loadDOM()

    def loadDOM(self):
        """loadDOM"""
        try:
            self.dom = xml.dom.minidom.parse(self.path)
        except (IOError, xml.parsers.expat.ExpatError):
            self.dom = xml.dom.minidom.parseString(
                util.getUserMenuXml(self.tree))
        util.removeWhitespaceNodes(self.dom)

    def load(self):
        """load"""
        if not self.tree.load_sync():
            raise ValueError("can not load menu tree %r" %
                             (self.tree.props.menu_basename,))

    def getMenus(self, parent):
        """getMenus"""
        if parent is None:
            yield (self.tree.get_root_directory(), True)
            return

        item_iter = parent.iter()
        item_type = item_iter.next()
        while item_type != GMenu.TreeItemType.INVALID:
            if item_type == GMenu.TreeItemType.DIRECTORY:
                item = item_iter.get_directory()
                yield (item, self.isVisible(item))
            item_type = item_iter.next()

    def getContents(self, item):
        """getContents"""
        contents = []
        item_iter = item.iter()
        item_type = item_iter.next()

        while item_type != GMenu.TreeItemType.INVALID:
            item = None
            if item_type == GMenu.TreeItemType.DIRECTORY:
                item = item_iter.get_directory()
            elif item_type == GMenu.TreeItemType.ENTRY:
                item = item_iter.get_entry()
            elif item_type == GMenu.TreeItemType.HEADER:
                item = item_iter.get_header()
            elif item_type == GMenu.TreeItemType.ALIAS:
                item = item_iter.get_alias()
            elif item_type == GMenu.TreeItemType.SEPARATOR:
                item = item_iter.get_separator()
            if item:
                contents.append(item)
            item_type = item_iter.next()
        return contents

    def writeMenu(self, menu, **kwargs):
        """Keep me around until NewDirectory is implemented"""
        if menu is not None:
            file_id = os.path.split(menu.get_desktop_file_path())[1]
            file_path = menu.get_desktop_file_path()
            keyfile = GLib.KeyFile()
            keyfile.load_from_file(file_path, util.KEY_FILE_FLAGS)
        elif menu is None and 'Name' not in kwargs:
            raise Exception('New menus need a name')
        else:
            file_id = util.getUniqueFileId(kwargs['Name'], '.directory')
            keyfile = GLib.KeyFile()

        util.fillKeyFile(keyfile, kwargs)

        contents, length = keyfile.to_data()

        path = os.path.join(util.getUserDirectoryPath(), file_id)
        with open(path, 'w') as f:
            f.write(contents)
        return file_id
