import os
import unicodedata
import lxml.etree as etree
import lxml.builder as builder


# https://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-normalize-in-a-python-unicode-string
# thanks to hexaJer for their answer
def strip_accents(text):
    """
    Strip accents from input String.

    :param text: The input string.
    :type text: String.

    :returns: The processed String.
    :rtype: String.
    """
    try:
        text = unicode(text, 'utf-8')
    except (TypeError, NameError): # unicode is a default on python 3 
        pass
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore')
    text = text.decode("utf-8")
    return str(text)


def get_author_list(item, nsmap):
    """
    Get a list of author last names in lowercase letters.

    :param item:
    :param nsmap:
    :return:
    """
    authorItem = item.find('{' + nsmap['bib'] + '}authors')
    authorSeq = authorItem.find('{' + nsmap['rdf'] + '}Seq')

    authorList = []
    for li in authorSeq.getchildren():
        person = li.find('{' + nsmap['foaf'] + '}Person')
        surname = person.find('{' + nsmap['foaf'] + '}surname').text

        authorList.append(strip_accents(surname).replace("'", '').replace('-', '').replace(' ', '').lower())

    return authorList


def get_year(item, nsmap):
    """
    Return the year an item was published.

    :param item:
    :param nsmap:
    :return:
    """
    return item.find('{' + nsmap['dc'] + '}date').text.split('-')[0]    


def format_pdf_name(item, nsmap):
    """
    Format the filename for an item, given the citation type and number of authors.

    :param item:
    :param nsmap:
    :return:
    """
    citType = item.tag.split('}')[-1]

    authors = get_author_list(item, nsmap)
    year = get_year(item, nsmap)

    if citType in ['Article', 'BookSection', 'Report']:
        subdir = year
    elif citType in ['Book']:
        subdir = 'books'
    elif citType in ['Thesis']:
        subdir = 'thesis'
        year = 'thesis'
    else:
        subdir = 'year'

    if len(authors) > 2:
        return os.path.join(subdir, authors[0] + 'etal' + year + '.pdf')
    elif len(authors) == 2:
        return os.path.join(subdir, authors[0] + 'and' + authors[1] + year + '.pdf')
    else:
        return os.path.join(subdir, authors[0] + year + '.pdf')


def get_link_key(item, nsmap):
    """
    Get the link key for an item.

    :param item:
    :param nsmap:
    :return:
    """
    link = item.find('{' + nsmap['link'] + '}link')
    if link is not None:
        keys = [key for key in link.keys() if '{' + nsmap['rdf'] + '}resource' in key]
        return link.get(keys[0])
    else:
        return None
    

def get_all_links(items, nsmap):
    """
    Get all of the link keys in a list of items.

    :param items:
    :param nsmap:
    :return:
    """
    all_keys = []
    for item in items:
        key = get_link_key(item, nsmap)
        if key is not None:
            all_keys.append(int(key.split('_')[-1]))
    return all_keys


def next_available_link(links):
    """
    Find the maximum item link value and add 1.

    :param links:
    :return:
    """
    links = [int(l) for l in links]
    links.sort()
    return links[-1] + 1


def make_attachment(item, nsmap, links, attachment_dir):
    """
    Make an Attachment object to add to the RDF tree.

    :param item:
    :param nsmap:
    :param links:
    :param attachment_dir:
    :return:
    """
    pdf_name = format_pdf_name(item, nsmap)

    if os.path.exists(os.path.join(attachment_dir, pdf_name)):
        E = builder.ElementMaker()

        if get_link_key(item, nsmap) is not None:
            this_key = get_link_key(item, nsmap)
        else:
            this_key = '#item_{}'.format(next_available_link(links))
            item = add_link(item, this_key, nsmap)
            links.append(next_available_link(links))

        # have to add z:itemType, dc:title, link:type
        attachment = E('{' + nsmap['z'] + '}Attachment')
        attachment.set('{' + nsmap['rdf'] + '}about', this_key)

        itemType = E('{' + nsmap['z'] + '}itemType')
        itemType.text = 'attachment'

        resource = E('{' + nsmap['rdf'] + '}resource')
        resource.set('{' + nsmap['rdf'] + '}resource', "attachments:{}".format(pdf_name))

        title = E('{' + nsmap['dc'] + '}title')
        title.text = os.path.basename(pdf_name)

        linkMode = E('{' + nsmap['z'] + '}linkMode')
        linkMode.text = '2'

        link = E('{' + nsmap['link'] + '}type')
        link.text = 'application/pdf'

        attachment.append(itemType)
        attachment.append(resource)
        attachment.append(title)
        attachment.append(linkMode)
        attachment.append(link)    

        return attachment, item, links
    else:
        print('Could not find {} in {}'.format(pdf_name, attachment_dir))
        return None, item, links


def add_link(item, key, nsmap):
    """
    Add a link attribute to an item.

    :param item:
    :param key:
    :param nsmap:
    :return:
    """
    # needs to look like: link:link rdf:resource=link_key
    E = builder.ElementMaker()

    thisLink = E('{' + nsmap['link'] + '}link')
    thisLink.set('{' + nsmap['rdf'] + '}resource', key)

    item.append(thisLink)
    return item


def add_attachments(fn_xml, fn_out, attachment_dir):
    """
    Read an xml file, find the filenames associated with each citation item, and attach them if they exist.

    :param fn_xml:
    :param fn_out:
    :param attachment_dir:
    :return:
    """
    tree = etree.parse(fn_xml)
    root = tree.getroot()
    nsmap = root.nsmap

    E = builder.ElementMaker()

    newRoot = E('{' + nsmap['rdf'] + '}RDF')

    bibItems = [c for c in root if root.nsmap['bib'] in c.tag]
    item_keys = get_all_links(bibItems, nsmap)

    for item in bibItems:
        if item.find('{' + nsmap['bib'] + '}authors') is not None:
            attachment, item, item_keys = make_attachment(item, nsmap, item_keys, attachment_dir)
            newRoot.append(item)
            if attachment is not None:
                newRoot.append(attachment)
        else:
            newRoot.append(item)

    outTree = etree.ElementTree(newRoot)
    outTree.write(fn_out, pretty_print=True, xml_declaration=False)

