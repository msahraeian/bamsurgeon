#!/bin/env python

"""
try to do ref-directed assembly for paired reads in a region of a .bam file
"""

import pysam,tempfile,argparse,subprocess,sys,shutil,os,re

def fastaContigs(fastaFile):
    fh = open(fastaFile, 'r')
    contigs = []
    name = None
    seq  = None 
    for line in fh:
        if re.search("^>", line):
            if name and seq:
                contigs.append(Contig(name,seq))
            name = line.lstrip('>').strip()
            seq = ''
        else:
            if name:
                seq += line.strip()
            else:
                raise ValueError("invalid fasta format: " + fastaFile)
    if name and seq:
        contigs.append(Contig(name,seq))
    return contigs

class Contig:
    def __init__(self,name,seq):
        self.name = name
        self.seq  = seq
        self.len  = len(seq)
        assert self.name
        assert self.seq
        assert self.len
    def __str__(self):
        return ">" + self.name + "\n" + self.seq 

def median(list):
    list.sort()
    i = len(list)/2
    if len(list) % 2 == 0:
        return (list[i] + list[i+1])/2
    else:
        return list[i]

def n50(contigs):
    ln = map(lambda x: x.len, contigs)
    nlist = []
    for n in ln:
        for i in range(n):
            nlist.append(n)
    return median(nlist)

def runVelvet(reads,refseqname,refseq,kmer,isPaired=True,long=False, inputContigs=False, cov_cutoff=False, noref=False):
    """
    reads is either a dictionary of ReadPair objects, (if inputContigs=False) or a list of 
    Contig objects (if inputContigs=True), refseq is a single sequence, kmer is an odd int
    """
    readsFasta  = tempfile.NamedTemporaryFile(delete=False)
    refseqFasta = tempfile.NamedTemporaryFile(delete=False)

    if inputContigs:
        for contig in reads:
            readsFasta.write(str(contig) + "\n")
    else:
        for readpair in reads.values():
            readsFasta.write(readpair.fasta())

    refseqFasta.write(">%s\n%s\n" % (refseqname,refseq))

    readsFasta.flush()
    refseqFasta.flush()

    readsFN  = readsFasta.name
    refseqFN = refseqFasta.name

    tmpdir = tempfile.mkdtemp()

    print tmpdir

    if noref:
        if long:
            argsvelveth = ['velveth', tmpdir, str(kmer), '-long', readsFN]
        else:
            argsvelveth = ['velveth', tmpdir, str(kmer), '-shortPaired', readsFN]
    else:
        if long: 
            argsvelveth = ['velveth', tmpdir, str(kmer), '-reference', refseqFN, '-long', readsFN]
        else:
            argsvelveth = ['velveth', tmpdir, str(kmer), '-reference', refseqFN, '-shortPaired', readsFN]

    if cov_cutoff:
        argsvelvetg = ['velvetg', tmpdir, '-exp_cov', 'auto', '-cov_cutoff', 'auto']
    else:
        argsvelvetg = ['velvetg', tmpdir]
        
    subprocess.call(argsvelveth)
    subprocess.call(argsvelvetg)

    return fastaContigs(tmpdir + "/contigs.fa")

    # cleanup
    shutil.rmtree(tmpdir)
    os.unlink(readsFN)
    os.unlink(refseqFN)

class ReadPair:
    def __init__(self,read,mate):
        assert read.is_read1 != mate.is_read1

        self.read1 = None
        self.read2 = None

        if read.is_read1:
            self.read1 = read
            self.read2 = mate
        else:
            self.read1 = mate
            self.read2 = read

    def fasta(self):
        return ">" + self.read1.qname + "\n" + self.read1.seq + "\n>" + self.read2.qname + "\n" + self.read2.seq + "\n"

    def __str__(self):
        r1map = "mapped"
        r2map = "mapped"

        if self.read1.is_unmapped:
            r1map = "unmapped"
        if self.read2.is_unmapped:
            r2map = "unmapped"

        output = " ".join(("read1:", self.read1.qname, self.read1.seq, r1map, "read2:", self.read2.qname, self.read2.seq, r2map))
        return output

def asm(chr, start, end, bamfile, matefile, reffile, kmersize, noref=False):
    readpairs = {}
    for read in bamfile.fetch(chr,start,end):
        if not read.mate_is_unmapped and read.is_paired:
            mate = matefile.mate(read)
            readpairs[read.qname] = ReadPair(read,mate)

    refseq = reffile.fetch(chr,start,end)

    region = chr + ":" + str(start) + "-" + str(end)

    contigs = runVelvet(readpairs, region, refseq, int(args.kmersize), cov_cutoff=True, noref=noref)
    newcontigs = None

    for contig in contigs:
        print contig

    if len(contigs) > 1:
        newcontigs = runVelvet(contigs, region, refseq, int(args.kmersize), long=True, inputContigs=True, noref=noref)

    if newcontigs and n50(newcontigs) > n50(contigs):
        contigs = newcontigs

    return contigs

def main(args):
    bamfile  = pysam.Samfile(args.bamFileName,'rb')
    matefile = pysam.Samfile(args.bamFileName,'rb')
    reffile  = pysam.Fastafile(args.refFasta)

    (chr,coords) = args.regionString.split(':')
    (start,end) = coords.split('-')
    start = int(start)
    end = int(end)

    contigs = asm(chr, start, end, bamfile, matefile, reffile, int(args.kmersize), args.noref)

    for contig in contigs:
        print contig

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='parse the output of pickreads.py')
    parser.add_argument('-f', '--fastaref', dest='refFasta', required=True,
                        help='indexed reference fo ref-directed assembly')
    parser.add_argument('-r', '--region', dest='regionString', required=True,
                        help='format: chrN:startbasenum-endbasenum')
    parser.add_argument('-b', '--bamfile', dest='bamFileName', required=True,
                        help='target .bam file, region specified in -r must exist')
    parser.add_argument('-k', '--kmersize', dest='kmersize', default=31,
                        help='kmer size for velvet, default=31')
    parser.add_argument('--noref', action="store_true")
    args = parser.parse_args()
    main(args)
