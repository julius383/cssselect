import re
from lxml import etree

class SelectorSyntaxError(Exception):
    pass

class ExpressionError(Exception):
    pass

class _UniToken(unicode):
    def __new__(cls, contents, pos):
        obj = unicode.__new__(cls, contents)
        obj.pos = pos
        return obj
        
    def __repr__(self):
        return '%s(%s, %r)' % (
            self.__class__.__name__,
            unicode.__repr__(self),
            self.pos)

class Symbol(_UniToken):
    pass

class String(_UniToken):
    pass

class Token(_UniToken):
    pass

############################################################
## Parsing
############################################################

##############################
## Syntax objects:

class Class(object):
    """
    Represents selector.class_name
    """

    def __init__(self, selector, class_name):
        self.selector = selector
        self.class_name = class_name

    def __repr__(self):
        return '%s[%r.%s]' % (
            self.__class__.__name__,
            self.selector,
            self.class_name)

    def xpath(self):
        sel_xpath = self.selector.xpath()
        sel_xpath.add_condition(
            "contains(concat(' ', normalize-space(@class), ' '), %s)" % xpath_repr(' '+self.class_name+' '))
        return sel_xpath

class Function(object):
    """
    Represents selector:name(expr)
    """

    unsupported = [
        'target', 'lang', 'enabled', 'disabled',]

    def __init__(self, selector, type, name, expr):
        self.selector = selector
        self.type = type
        self.name = name
        self.expr = expr

    def __repr__(self):
        return '%s[%r%s%s(%r)]' % (
            self.__class__.__name__,
            self.selector,
            self.type, self.name, self.expr)

    def xpath(self):
        sel_path = self.selector.xpath()
        if self.name in self.unsupported:
            raise ExpressionError(
                "The psuedo-class %r is not supported" % self.name)
        method = '_xpath_' + self.name.replace('-', '_')
        if not hasattr(self, method):
            raise ExpressionError(
                "The psuedo-class %r is unknown" % self.name)
        method = getattr(self, method)
        return method(sel_path, self.expr)

    def _xpath_nth_child(self, xpath, expr, last=False):
        if isinstance(expr, int):
            return self._xpath_nth_child_simple(xpath, expr, last)
        if not isinstance(expr, int):
            a, b = parse_series(expr)
            if not a:
                # a=0 means nothing is returned...
                xpath.add_condition('false()')
                return xpath
            if a == 1:
                return self._xpath_nth_child_simple(xpath, expr, last)
            if b > 0:
                b_neg = str(-b)
            else:
                b_neg = '+%s' % (-b)
            expr = '(position() %s) mod %s = 0' % (b_neg, a)
            if b >= 0:
                expr += ' and position() >= %s' % b
            xpath.add_condition(expr)
            return xpath
            # FIXME: handle an+b, odd, even
            # an+b means every-a, plus b, e.g., 2n+1 means odd
            # 0n+b means b
            # n+0 means a=1, i.e., all elements
            # an means every a elements, i.e., 2n means even
            # -n means -1n
            # -1n+6 means elements 6 and previous

    def _xpath_nth_child_simple(self, xpath, expr, last=False):
        if isinstance(expr, int):
            expr -= 1
            if last:
                expr = 'last() - %s' % expr
            xpath = XPath('*/%s' % xpath)
            xpath.add_index(expr)
            return xpath

    def _xpath_nth_last_child(self, xpath, expr):
        return self._xpath_nth_child(xpath, expr, last=True)

    def _xpath_nth_of_type(self, xpath, expr, last=False):
        # Like nth-of-type, but only for *this* type
        if isinstance(expr, int):
            expr -= 1
            if last:
                expr = 'last() - %s' % expr
            xpath = XPath('*/%s' % xpath)
            xpath.add_index(expr)
            return xpath
        else:
            raise NotImplementedError

    def _xpath_nth_last_of_type(self, xpath, expr):
        return self._xpath_nth_of_type(xpath, expr, last=True)

    def _xpath_contains(self, xpath, expr):
        # text content, minus tags, must contain expr
        if isinstance(expr, Element):
            expr = expr._format_element()
        xpath.add_condition('contains(css:lower-case(string(.)), %s)'
                            % xpath_repr(expr.lower()))
        return xpath

    def _xpath_not(self, xpath, expr):
        # everything for which not expr applies
        expr = expr.xpath()
        cond = expr.condition
        # FIXME: should I do something about element_path?
        xpath.add_condition('not(%s)' % cond)
        return xpath

def _make_lower_case(context, s):
    return s.lower()

etree.FunctionNamespace("css")['lower-case'] = _make_lower_case

class Pseudo(object):
    """
    Represents selector:ident
    """

    unsupported = ['indeterminate', 'first-line', 'first-letter',
                   'selection', 'before', 'after', 'link', 'visited',
                   'active', 'focus', 'hover']

    def __init__(self, element, type, ident):
        self.element = element
        assert type in (':', '::')
        self.type = type
        self.ident = ident

    def __repr__(self):
        return '%s[%r%s%s]' % (
            self.__class__.__name__,
            self.element,
            self.type, self.ident)

    def xpath(self):
        el_xpath = self.element.xpath()
        if self.ident in self.unsupported:
            raise ExpressionError(
                "The psuedo-class %r is unsupported" % self.ident)
        method = '_xpath_' + self.ident.replace('-', '_')
        if not hasattr(self, method):
            raise ExpressionError(
                "The psuedo-class %r is unknown" % self.ident)
        method = getattr(self, method)
        el_xpath = method(el_xpath)
        return el_xpath

    def _xpath_checked(self, xpath):
        xpath.add_condition("(@selected or @checked) and (node-name(.) = 'input' or node-name(.) = 'option')")
        return xpath

    def _xpath_root(self, xpath):
        # if this element is the root element
        raise NotImplementedError

    def _xpath_first_child(self, xpath):
        xpath = XPath('*/%s' % xpath)
        xpath.add_condition('position() = 0')
        return xpath

    def _xpath_last_child(self, xpath):
        xpath = XPath('*/%s' % xpath)
        xpath.add_condition('position() = last()')
        return xpath

    def _xpath_first_of_type(self, xpath):
        xpath = XPath('*/%s' % xpath)
        xpath.add_index(0)
        return xpath

    def _xpath_last_of_type(self, xpath):
        xpath.add_index('last()')
        return xpath

    def _xpath_only_child(self, xpath):
        xpath.add_condition('count(..) = 1')
        return xpath

    def _xpath_only_of_type(self, xpath):
        # FIXME: I doubt this is right
        xpath.add_condition('count(../node-name(.)) = 1')
        return xpath

    def _xpath_empty(self, xpath):
        xpath.add_condition("count(.) = 0 and string(.) = ''")
        return xpath

class Attrib(object):
    """
    Represents selector[namespace|attrib operator value]
    """

    def __init__(self, selector, namespace, attrib, operator, value):
        self.selector = selector
        self.namespace = namespace
        self.attrib = attrib
        self.operator = operator
        self.value = value

    def __repr__(self):
        if self.operator == 'exists':
            return '%s[%r[%s]]' % (
                self.__class__.__name__,
                self.selector,
                self._format_attrib())
        else:
            return '%s[%r[%s %s %r]]' % (
                self.__class__.__name__,
                self.selector,
                self._format_attrib(),
                self.operator,
                self.value)

    def _format_attrib(self):
        if self.namespace == '*':
            return self.attrib
        else:
            return '%s|%s' % (self.namespace, self.attrib)

    def _xpath_attrib(self):
        # FIXME: if attrib is *?
        if self.namespace == '*':
            return '@' + self.attrib
        else:
            return '@%s:%s' % (self.namespace, self.attrib)

    def xpath(self):
        path = self.selector.xpath()
        attrib = self._xpath_attrib()
        value = self.value
        if self.operator == 'exists':
            assert not value
            path.add_condition(attrib)
        elif self.operator == '=':
            path.add_condition('%s = %s' % (attrib,
                                            xpath_repr(value)))
        elif self.operator == '!=':
            # FIXME: this seems like a weird hack...
            if value:
                path.add_condition('not(%s) or %s != %s'
                                   % (attrib, attrib, xpath_repr(value)))
            else:
                path.add_condition('%s != %s'
                                   % (attrib, xpath_repr(value)))
            #path.add_condition('%s != %s' % (attrib, xpath_repr(value)))
        elif self.operator == '~=':
            path.add_condition("contains(concat(' ', normalize-space(%s), ' '), %s)" % (attrib, xpath_repr(' '+value+' ')))
        elif self.operator == '|=':
            # Weird, but true...
            path.add_condition('%s = %s or starts-with(%s, %s)' % (
                attrib, xpath_repr(value),
                attrib, xpath_repr(value + '-')))
        elif self.operator == '^=':
            path.add_condition('starts-with(%s, %s)' % (
                attrib, xpath_repr(value)))
        elif self.operator == '$=':
            # Oddly there is a starts-with in XPath 1.0, but not ends-with
            path.add_condition('substring(%s, string-length(%s)-%s) = %s'
                               % (attrib, attrib, len(value)-1, xpath_repr(value)))
        elif self.operator == '*=':
            path.add_condition('contains(%s, %s)' % (
                attrib, xpath_repr(value)))
        else:
            assert 0, ("Unknown operator: %r" % self.operator)
        return path

class Element(object):
    """
    Represents namespace|element
    """

    def __init__(self, namespace, element):
        self.namespace = namespace
        self.element = element

    def __repr__(self):
        return '%s[%s]' % (
            self.__class__.__name__,
            self._format_element())

    def _format_element(self):
        if self.namespace == '*':
            return self.element
        else:
            return '%s|%s' % (self.namespace, self.element)

    def xpath(self):
        if self.namespace == '*':
            return XPath(self.element.lower())
        else:
            return XPath('%s:%s' % (self.namespace, self.element))

class Hash(object):
    """
    Represents selector#id
    """

    def __init__(self, selector, id):
        self.selector = selector
        self.id = id

    def __repr__(self):
        return '%s[%r#%s]' % (
            self.__class__.__name__,
            self.selector, self.id)

    def xpath(self):
        path = self.selector.xpath()
        path.add_condition('@id=%s' % xpath_repr(self.id))
        return path

class Or(object):

    def __init__(self, items):
        self.items = items
    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            self.items)    

    def xpath(self):
        paths = [item.xpath() for item in self.items]
        return XPathOr(paths)

class CombinedSelector(object):

    _method_mapping = {
        ' ': 'descendant',
        '>': 'child',
        '+': 'direct_adjacent',
        '~': 'indirect_adjacent',
        }

    def __init__(self, selector, combinator, subselector):
        assert selector is not None
        self.selector = selector
        self.combinator = combinator
        self.subselector = subselector

    def __repr__(self):
        if self.combinator == ' ':
            comb = '<followed>'
        else:
            comb = self.combinator
        return '%s[%r %s %r]' % (
            self.__class__.__name__,
            self.selector,
            comb,
            self.subselector)

    def xpath(self):
        if self.combinator not in self._method_mapping:
            raise ExpressionError(
                "Unknown combinator: %r" % self.combinator)
        method = '_xpath_' + self._method_mapping[self.combinator]
        method = getattr(self, method)
        path = self.selector.xpath()
        return method(path, self.subselector)

    def _xpath_descendant(self, xpath, sub):
        # when sub is a descendant in any way of xpath
        return XPath('%s/descendant::%s' % (xpath, sub.xpath()))

    def _xpath_child(self, xpath, sub):
        # when sub is an immediate child of xpath
        return XPath(str(xpath) + '/' + str(sub.xpath()))

    def _xpath_direct_adjacent(self, xpath, sub):
        # when sub immediately follows xpath
        path = self._xpath_indirect_adjacent(xpath, sub)
        path.add_index(0)
        return path

    def _xpath_indirect_adjacent(self, xpath, sub):
        # when sub comes somewhere after xpath as a sibling
        return XPath('%s/following-sibling::%s' % (
            xpath, sub.xpath()))


##############################
## XPath objects:

def xpath(css_expr, prefix='descendant-or-self::'):
    if isinstance(css_expr, basestring):
        css_expr = parse(css_expr)
    expr = css_expr.xpath()
    assert expr is not None, (
        "Got None for xpath expression from %s" % repr(css_expr))
    if isinstance(expr, XPathOr):
        for item in expr.items:
            item.element_path = prefix + item.element_path
    else:
        expr.element_path = prefix + expr.element_path
    return str(expr)

def run_xpath(doc, xpath):
    return [el for el in doc.xpath(xpath)
            if isinstance(el, etree.ElementBase)]

def run_css(doc, css):
    return run_xpath(doc, xpath(css))

class XPath(object):

    def __init__(self, element_path, condition=None):
        self.element_path = element_path
        self.condition = condition

    def __str__(self):
        path = str(self.element_path)
        if self.condition:
            path += '[%s]' % self.condition
        return path

    def __repr__(self):
        return '%s[%s]' % (
            self.__class__.__name__, self)

    def add_condition(self, condition):
        if self.condition:
            self.condition = '%s and (%s)' % (self.condition, condition)
        else:
            self.condition = condition

    def add_index(self, index):
        self.element_path = '%s[%s]' % (self.element_path, index)

class XPathOr(XPath):

    """
    Represents on |'d expressions.  Note that unfortunately it isn't
    the union, it's the sum, so duplicate elements will appear.
    """

    def __init__(self, items):
        for item in items:
            assert item is not None
        self.items = items

    def __str__(self):
        return ' | '.join(map(str, self.items))


def xpath_repr(s):
    # FIXME: I don't think this is right
    if isinstance(s, Element):
        # This is probably a symbol that looks like an expression...
        s = s._format_element()
    return repr(str(s))

##############################
## Parsing functions

def parse(string):
    stream = TokenStream(tokenize(string))
    stream.source = string
    try:
        return parse_selector_group(stream)
    except SelectorSyntaxError, e:
        e.args = tuple(["%s at %s -> %s" % (
            e, stream.used, list(stream))])
        raise

def parse_selector_group(stream):
    result = []
    while 1:
        result.append(parse_selector(stream))
        if stream.peek() == ',':
            stream.next()
        else:
            break
    if len(result) == 1:
        return result[0]
    else:
        return Or(result)

def parse_selector(stream):
    result = parse_simple_selector(stream)
    while 1:
        peek = stream.peek()
        if peek == ',' or peek == ')' or peek is None:
            return result
        if stream.peek() in ('+', '>', '~'):
            # A combinator
            combinator = stream.next()
        else:
            combinator = ' '
        next_selector = parse_simple_selector(stream)
        result = CombinedSelector(result, combinator, next_selector)
    return result

def parse_simple_selector(stream):
    peek = stream.peek()
    if peek != '*' and not isinstance(peek, Symbol):
        element = namespace = '*'
    else:
        next = stream.next()
        if next != '*' and not isinstance(next, Symbol):
            raise SelectorSyntaxError(
                "Expected symbol, got %r" % next)
        if stream.peek() == '|':
            namespace = next
            stream.next()
            element = stream.next()
            if element != '*' and not isinstance(next, Symbol):
                raise SelectorSyntaxError(
                    "Expected symbol, got %r" % next)
        else:
            namespace = '*'
            element = next
    result = Element(namespace, element)
    has_hash = False
    while 1:
        peek = stream.peek()
        if peek == '#':
            if has_hash:
                # You can't have two hashes
                # (FIXME: is there some more general rule I'm missing?)
                break
            stream.next()
            result = Hash(result, stream.next())
            has_hash = True
            continue
        elif peek == '.':
            stream.next()
            result = Class(result, stream.next())
            continue
        elif peek == '[':
            stream.next()
            result = parse_attrib(result, stream)
            next = stream.next()
            if not next == ']':
                raise SelectorSyntaxError(
                    "] expected, got %r" % next)
            continue
        elif peek == ':' or peek == '::':
            type = stream.next()
            ident = stream.next()
            if not isinstance(ident, Symbol):
                raise SelectorSyntaxError(
                    "Expected symbol, got %r" % ident)
            if stream.peek() == '(':
                stream.next()
                peek = stream.peek()
                if isinstance(peek, String):
                    selector = stream.next()
                elif isinstance(peek, Symbol) and is_int(peek):
                    selector = int(stream.next())
                else:
                    # FIXME: parse_simple_selector, or selector, or...?
                    selector = parse_simple_selector(stream)
                    next = stream.next()
                    if not next == ')':
                        raise SelectorSyntaxError(
                            "Expected ), got %r and %r"
                            % (next, selector))
                result = Function(result, type, ident, selector)
            else:
                result = Pseudo(result, type, ident)
            continue
        else:
            break
        # FIXME: not sure what "negation" is
    return result

def is_int(v):
    try:
        int(v)
    except ValueError:
        return False
    else:
        return True

def parse_attrib(selector, stream):
    attrib = stream.next()
    if stream.peek() == '|':
        namespace = attrib
        stream.next()
        attrib = stream.next()
    else:
        namespace = '*'
    if stream.peek() == ']':
        return Attrib(selector, namespace, attrib, 'exists', None)
    op = stream.next()
    if not op in ('^=', '$=', '*=', '=', '~=', '|=', '!='):
        raise SelectorSyntaxError(
            "Operator expected, got %r" % op)
    value = stream.next()
    if not isinstance(value, (Symbol, String)):
        raise SelectorSyntaxError(
            "Expected string or symbol, got %r" % value)
    return Attrib(selector, namespace, attrib, op, value)

def parse_series(s):
    """
    Parses things like '1n+2', or 'an+b' generally, returning (a, b)
    """
    if isinstance(s, Element):
        s = s._format_element()
    if isinstance(s, int):
        # Happens when you just get a number
        return (1, s)
    if s == 'odd':
        return (2, 1)
    elif s == 'even':
        return (2, 0)
    if 'n' not in s:
        # Just a b
        return int(s)
    a, b = s.split('n', 1)
    if not a:
        a = 1
    elif a == '-' or a == '+':
        a = int(a+'1')
    else:
        a = int(a)
    if not b:
        b = 0
    elif b == '-' or b == '+':
        b = int(b+'1')
    else:
        b = int(b)
    return (a, b)
    

############################################################
## Tokenizing
############################################################

_whitespace_re = re.compile(r'\s+')

_comment_re = re.compile(r'/\*.*?\*/', re.S)

_count_re = re.compile(r'[+-]?\d*n(?:[+-]\d+)?')

def tokenize(s):
    pos = 0
    s = _comment_re.sub('', s)
    while 1:
        match = _whitespace_re.match(s, pos=pos)
        if match:
            pos = match.end()
        if pos >= len(s):
            return
        match = _count_re.match(s, pos=pos)
        if match and match.group() != 'n':
            sym = s[pos:match.end()]
            yield Symbol(sym, pos)
            pos = match.end()
            continue
        c = s[pos]
        c2 = s[pos:pos+2]
        if c2 in ('~=', '|=', '^=', '$=', '*=', '::', '!='):
            yield Token(c2, pos)
            pos += 2
            continue
        if c in '>+~,.*=[]()|:#':
            yield Token(c, pos)
            pos += 1
            continue
        if c == '"' or c == "'":
            # Quoted string
            old_pos = pos
            sym, pos = tokenize_escaped_string(s, pos)
            yield String(sym, old_pos)
            continue
        old_pos = pos
        sym, pos = tokenize_symbol(s, pos)
        yield Symbol(sym, old_pos)
        continue

def tokenize_escaped_string(s, pos):
    quote = s[pos]
    assert quote in ('"', "'")
    pos = pos+1
    start = pos
    while 1:
        next = s.find(quote, pos)
        if next == -1:
            raise SelectorSyntaxError(
                "Expected closing %s for string in: %r"
                % (quote, s[start:]))
        result = s[start:next]
        try:
            result = result.decode('unicode_escape')
        except UnicodeDecodeError:
            # Probably a hanging \
            pos = next+1
        else:
            return result, next+1
    
_illegal_symbol = re.compile(r'[^\w\\-]', re.UNICODE)

def tokenize_symbol(s, pos):
    start = pos
    match = _illegal_symbol.search(s, pos=pos)
    if not match:
        # Goes to end of s
        return s[start:], len(s)
    if match.start() == pos:
        assert 0, (
            "Unexpected symbol: %r at %s" % (s[pos], pos))
    if not match:
        result = s[start:]
        pos = len(s)
    else:
        result = s[start:match.start()]
        pos = match.start()
    try:
        result = result.decode('unicode_escape')
    except UnicodeDecodeError, e:
        raise SelectorSyntaxError(
            "Bad symbol %r: %s" % (result, e))
    return result, pos

class TokenStream(object):

    def __init__(self, tokens, source=None):
        self.used = []
        self.tokens = iter(tokens)
        self.source = source
        self.peeked = None
        self._peeking = False

    def next(self):
        if self._peeking:
            self._peeking = False
            self.used.append(self.peeked)
            return self.peeked
        else:
            try:
                next = self.tokens.next()
                self.used.append(next)
                return next
            except StopIteration:
                return None

    def __iter__(self):
        return iter(self.next, None)

    def peek(self):
        if not self._peeking:
            try:
                self.peeked = self.tokens.next()
            except StopIteration:
                return None
            self._peeking = True
        return self.peeked
