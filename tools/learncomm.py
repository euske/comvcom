#!/usr/bin/env python
##
##  learncomm.py
##
##  Training:
##    $ learncomm.py -k prop comments.feats > out.tree
##  Testing:
##    $ learncomm.py -k prop -f out.tree comments.feats
##
import sys
from math import log2
from comment import CommentEntry


def calcetp(values):
    n = sum(values)
    etp = sum( v*log2(n/v) for v in values ) / n
    return etp

def countkeys(ents):
    d = {}
    for e in ents:
        k = e.key
        if k in d:
            d[k] += 1
        else:
            d[k] = 1
    return d

def bestkey(keys):
    maxkey = None
    maxv = 0
    for (k,v) in keys.items():
        if maxkey is None or maxv < v:
            maxkey = k
            maxv = v
    assert maxkey is not None
    return maxkey

def entetp(ents):
    return calcetp(countkeys(ents).values())


##  Feature
##
class Feature:

    class InvalidSplit(ValueError): pass

    def __init__(self, name, attr):
        self.name = name
        self.attr = attr
        return

    def __repr__(self):
        return ('<%s: %s>' % (self.__class__.__name__, self.name))

    def get(self, e):
        return e[self.attr]

    def split(self, ents):
        raise NotImplementedError

    def ident(self, arg, e):
        raise NotImplementedError

##  DiscreteFeature
##
class DiscreteFeature(Feature):

    def __init__(self, attr, prefix='DF:'):
        Feature.__init__(self, prefix+attr, attr)
        return

    def ident(self, arg, e):
        return self.get(e)

    def split(self, ents):
        assert 2 <= len(ents)
        d = {}
        for e in ents:
            v = self.get(e)
            if v in d:
                d[v].append(e)
            else:
                d[v] = [e]
        if len(d) < 2: raise self.InvalidSplit
        n = len(ents)
        avgetp = sum( len(es) * entetp(es) for es in d.values() ) / n
        split = list(d.items())
        return (avgetp, None, split)

DF = DiscreteFeature

##  DiscreteFeatureOne
##
class DiscreteFeatureOne(DiscreteFeature):

    def __init__(self, attr, index=0):
        self.index = index
        DiscreteFeature.__init__(self, attr, 'DF%d:' % index)
        return

    def get(self, e):
        v = e[self.attr]
        if v is None: return None
        f = v.split(',')
        if len(f) <= self.index: return None
        return f[self.index]

DF1 = DiscreteFeatureOne

##  MembershipFeature
##
class MembershipFeature(Feature):

    def __init__(self, attr, prefix='MF:'):
        Feature.__init__(self, prefix+attr, attr)
        return

    def get(self, e):
        v = e[self.attr]
        if v is None: return []
        return v.split(',')

    def ident(self, arg, e):
        return arg in self.get(e)

    def split(self, ents):
        assert 2 <= len(ents)
        d = {}
        for e in ents:
            for v in self.get(e):
                if v in d:
                    es = d[v]
                else:
                    es = d[v] = set()
                es.add(e)
        if len(d) < 2: raise self.InvalidSplit
        n = len(ents)
        minsplit = minetp = None
        for (v,es) in d.items():
            nes = [ e for e in ents if e not in es ]
            if not nes: continue
            avgetp = (len(es)*entetp(es) + len(nes)*entetp(nes)) / n
            if minsplit is None or avgetp < minetp:
                minetp = avgetp
                minsplit = (v, nes)
        if minsplit is None: raise self.InvalidSplit
        (arg, nes) = minsplit
        split = [(True, list(d[arg])), (False, nes)]
        return (minetp, arg, split)

MF = MembershipFeature

##  MembershipFeatureOne
##
class MembershipFeatureOne(MembershipFeature):

    def __init__(self, attr, nmems=1):
        self.nmems = nmems
        MembershipFeature.__init__(self, attr, 'MF%d:' % nmems)
        return

    def get(self, e):
        v = e[self.attr]
        if v is None: return []
        return v.split(',')[:self.nmems]

MF1 = MembershipFeatureOne

##  QuantitativeFeature
##
class QuantitativeFeature(Feature):

    def __init__(self, attr, prefix='QF:'):
        Feature.__init__(self, prefix+attr, attr)
        return

    def ident(self, arg, e):
        v = self.get(e)
        if v is None:
            return 'un'
        elif v < arg:
            return 'lt'
        else:
            return 'ge'

    def split(self, ents):
        assert 2 <= len(ents)
        pairs = []
        undefs = []
        for e in ents:
            v = self.get(e)
            if v is None:
                undefs.append(e)
            else:
                pairs.append((e, v))
        if not pairs: raise self.InvalidSplit
        pairs.sort(key=(lambda ev: ev[1]))
        es = [ e for (e,_) in pairs ]
        vs = [ v for (_,v) in pairs ]
        n = len(pairs)
        minsplit = minetp = None
        v0 = vs[0]
        for i in range(1, n):
            v1 = vs[i]
            if v0 == v1: continue
            v0 = v1
            avgetp = (i * entetp(es[:i]) + (n-i) * entetp(es[i:])) / n
            if minsplit is None or avgetp < minetp:
                minetp = avgetp
                minsplit = i
        if minsplit is None: raise self.InvalidSplit
        arg = vs[minsplit]
        split = [('lt', es[:minsplit]), ('ge', es[minsplit:])]
        if undefs:
            split.append(('un', undefs))
        return (minetp, arg, split)

QF = QuantitativeFeature


##  TreeBranch
##
class TreeBranch:

    def __init__(self, feature, arg, default, children):
        self.feature = feature
        self.arg = arg
        self.default = default
        self.children = children
        return

    def __repr__(self):
        return ('<TreeBranch(%r, %r)>' %
                (self.feature, self.arg))

    def test(self, e):
        v = self.feature.ident(self.arg, e)
        try:
            branch = self.children[v]
            return branch.test(e)
        except KeyError:
            #print ('Unknown value: %r: %r' % (self.feature, v))
            return self.default

    def dump(self, depth=0):
        ind = '  '*depth
        print ('%sBranch %r: %r, default=%r' %
               (ind, self.feature, self.arg, self.default))
        for (v,branch) in self.children.items():
            print ('%s Value: %r ->' % (ind, v))
            branch.dump(depth+1)
        return

##  TreeLeaf
##
class TreeLeaf:

    def __init__(self, key):
        self.key = key
        return

    def __repr__(self):
        return ('<TreeLeaf(%r)>' % (self.key))

    def test(self, e):
        return self.key

    def dump(self, depth=0):
        ind = '  '*depth
        print ('%sLeaf %r' % (ind, self.key))
        return


##  TreeBuilder
##
class TreeBuilder:

    def __init__(self, minkeys=10, minetp=0.10, debug=1):
        self.features = {}
        self.minkeys = minkeys
        self.minetp = minetp
        self.debug = debug
        return

    def addfeat(self, feat):
        self.features[feat.name] = feat
        return

    def import_tree(self, tree):
        if isinstance(tree, tuple):
            (name, arg, default, children) = tree
            children = { v: self.import_tree(branch) for (v,branch) in children }
            return TreeBranch(self.features[name], arg, default, children)
        else:
            return TreeLeaf(tree)

    def build(self, ents, depth=0):
        keys = countkeys(ents)
        etp = calcetp(keys.values())
        ind = '  '*depth
        if self.debug:
            print ('%sBuild: %r, etp=%.3f' % (ind, keys, etp))
        if etp < self.minetp:
            if self.debug:
                print ('%s Too little entropy. Stopping.' % ind)
            return None
        if len(ents) < self.minkeys:
            if self.debug:
                print ('%s Too few keys. Stopping.' % ind)
            return None
        minbranch = minetp = None
        for feat in self.features.values():
            try:
                (etp, arg, split) = feat.split(ents)
            except Feature.InvalidSplit:
                continue
            if minbranch is None or etp < minetp:
                minetp = etp
                minbranch = (feat, arg, split)
        if minbranch is None:
            if self.debug:
                print ('%s No discerning feature. Stopping.' % ind)
            return None
        (feat, arg, split) = minbranch
        if self.debug:
            print ('%sFeature: %r, arg=%r, etp=%.3f' % (ind, feat, arg, etp))
        default = bestkey(keys)
        children = {}
        for (i,(v,es)) in enumerate(split):
            if 2 <= self.debug:
                r = [ (e[feat.attr], e.key) for e in es ]
                print ('%s Split%d (%d): %r, %r' % (ind, i, len(r), v, r))
            if self.debug:
                print ('%s Value: %r ->' % (ind, v))
            branch = self.build(es, depth+1)
            if branch is None:
                keys = countkeys(es)
                best = bestkey(keys)
                if self.debug:
                    print ('%s Leaf: %r -> %r' % (ind, v, best))
                branch = TreeLeaf(best)
            children[v] = branch
        return TreeBranch(feat, arg, default, children)


# export_tree
def export_tree(tree):
    if isinstance(tree, TreeBranch):
        children = [ (v, export_tree(branch))
                     for (v,branch) in tree.children.items() ]
        return (tree.feature.name, tree.arg, tree.default, children)
    else:
        return (tree.key)

def add_target_feats(builder):
    builder.addfeat(QF('deltaLine'))
    builder.addfeat(QF('deltaCols'))
    builder.addfeat(QF('deltaLeft'))
    builder.addfeat(QF('deltaRight'))
    builder.addfeat(DF1('rightTypes'))
    builder.addfeat(MF1('rightTypes'))
    builder.addfeat(MF('rightTypes'))
    builder.addfeat(MF1('words'))
    return

def add_cat_feats(builder):
    builder.addfeat(DF('type'))
    builder.addfeat(DF1('parentTypes'))
    builder.addfeat(MF1('parentTypes'))
    builder.addfeat(MF('parentTypes'))
    builder.addfeat(DF1('leftTypes'))
    builder.addfeat(MF1('leftTypes'))
    builder.addfeat(MF('leftTypes'))
    builder.addfeat(DF('codeLike'))
    builder.addfeat(DF('empty'))
    builder.addfeat(DF1('posTags'))
    builder.addfeat(MF1('posTags'))
    builder.addfeat(MF('posTags'))
    return

# main
def main(argv):
    import getopt
    import fileinput
    def usage():
        print('usage: %s [-d] [-m minkeys] [-f feats] [-k keyprop] [file ...]' %
              argv[0])
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'dm:f:k:')
    except getopt.GetoptError:
        return usage()
    debug = 0
    minkeys = 10
    feats = None
    keyprop = 'key'
    for (k, v) in opts:
        if k == '-d': debug += 1
        elif k == '-m': minkeys = int(v)
        elif k == '-f': feats = v
        elif k == '-k': keyprop = v

    builder = TreeBuilder(minkeys=minkeys, debug=debug)
    add_cat_feats(builder)

    fp = fileinput.input(args)
    ents = []
    for e in CommentEntry.load(fp):
        e.key = e[keyprop]
        assert e.key is not None
        line = int(e['line'])
        cols = int(e['cols'])
        if 'prevLine' in e:
            e['deltaLine'] = line - int(e['prevLine'])
        if 'prevCols' in e:
            e['deltaCols'] = cols - int(e['prevCols'])
        if 'leftLine' in e:
            e['deltaLeft'] = line - int(e['leftLine'])
        if 'rightLine' in e:
            e['deltaRight'] = line - int(e['rightLine'])
        ents.append(e)

    if feats is None:
        # training
        root = builder.build(ents)
        if debug:
            print()
            root.dump()
        print (export_tree(root))
    else:
        # testing
        with open(feats) as fp:
            data = eval(fp.read())
        tree = builder.import_tree(data)
        correct = {}
        keys = {}
        resp = {}
        for e in ents:
            keys[e.key] = keys.get(e.key,0)+1
            key = tree.test(e)
            resp[key] = resp.get(key,0)+1
            if e.key == key:
                correct[key] = correct.get(key,0)+1
        for (k,v) in correct.items():
            p = v/resp[k]
            r = v/keys[k]
            f = 2*(p*r)/(p+r)
            print ('%s: prec=%.3f(%d/%d), recl=%.3f(%d/%d), F=%.3f' %
                   (k, p, v, resp[k], r, v, keys[k], f))
        print ('%d/%d' % (sum(correct.values()), sum(keys.values())))
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
