import multiprocessing

from flib.core.gmt import GMT
from scipy import stats

from overrep_ouput_writer import OUT
from utilities.background import BACKGROUND

'''
2x2 contingency table for over representation tests

______________________________Gene List_______________________Genome________________
In Annotations     |    list_anno_overlaps    |       genome_anno_overlaps         |
------------------------------------------------------------------------------------
Not in Annotations |    list_genome_overlaps  |          genome_only               |
------------------------------------------------------------------------------------

http://bg.upf.edu/course-bco/documents/enrichment.pdf

MULTIPROCESSING:
-Passes in a map_arr storing a list of inputs 
-Used to condense GO term comparison loop

must first call build_inputs() to generate data inputs
call multiprocess() to generate output
'''

# each stat test will return an array of EnrichmentResults
class OverrepResult:
    def __init__(self, gsid, sample_set_ngenes, anno_id, anno_ngenes, p_value, overlaps, FDR):
        self.gsid = gsid
        self.sample_set_ngenes = sample_set_ngenes
        self.anno_id = anno_id
        self.anno_ngenes = anno_ngenes
        self.p_value = p_value
        self.overlaps = overlaps
        self.FDR = FDR

# each stat test will require an array of InputItems
class InputItem:
    def __init__(self, anno_id, anno_list, background, gsid, gene_set):
        self.anno_id = anno_id
        self.anno_list = anno_list
        self.background = background
        self.gsid = gsid
        self.gene_set = gene_set


# generates a list of inputs to be mapped to several processors
# each parameter will be an array of terms
def generate_inputs(anno, background):
    input_items = []
    for anno_id in anno.genesets:
        input_items.append([anno_id, anno.genesets[anno_id], background])
    return input_items


# completes the input array for each sepcific sample gene set and executes a multiprocess mapping inputs to all GO gene sets
def multiprocess(gsid, sample, map_arr, method):
    input_items = []
    for i, row in enumerate(map_arr):
        anno_id = row[0]
        anno_list = row[1]
        background = row[2]
        next_item = InputItem(anno_id, anno_list, background, gsid, sample.genesets[gsid])
        input_items.append(next_item)

    p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    results = p.map(method, input_items)
    p.close()
    p.join()

    return results


# generate contingency table
def gen_table(sample_set, anno_set, background):
    if background is None:
        background = BACKGROUND(anno_set.intersection(sample_set))

    list_anno_overlaps = len(sample_set.intersection(anno_set))
    if list_anno_overlaps == 0:
        return 0
    # background_size = len(sample_set) + len(anno_set) - list_anno_overlaps if background == None else len(background.background_genes)
    # backup code for other specifications
    background_size = len(background.background_genes)

    list_genome_overlaps = len(sample_set) - list_anno_overlaps
    # genome_anno_overlaps = len(anno_set.intersection(background.background_genes)) if background != None else len(anno_set)
    # backup code for other specifications
    genome_anno_overlaps = len(anno_set.intersection(background.background_genes))
    genome_only = background_size - genome_anno_overlaps

    return [[list_anno_overlaps, genome_anno_overlaps], [list_genome_overlaps, genome_only]]


# fisher exact test on 2x2 contingency tables
def fisher_exact(sample_sets, anno, alpha, background):
    gene_rankings = []
    # construct and analyze contingency tables
    map_arr = generate_inputs(anno, background)

    for gsid in sample_sets.genesets:
        input_items = multiprocess(gsid, sample_sets, map_arr, fisher_process)
        for input_item in input_items:
            gene_rankings.append(input_item)
    final_rankings = benjamini_hochberg(gene_rankings)
    return [final_rankings, significance_filter(final_rankings, alpha)]


# fisher sub-method for multiprocessing
def fisher_process(input_item):
    cont_table = gen_table(input_item.gene_set, input_item.anno_list, input_item.background)

    # in the case of no overlaps
    if cont_table == 0:
        return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list),1.0, 0, 0)
    list_anno_overlaps = cont_table[0][0]
    p_value = stats.fisher_exact(cont_table)[1]

    return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list),p_value, list_anno_overlaps, 0)


# hypergeometric test on 2x2 contingency tables
def hypergeometric(sample_sets, anno, alpha, background):
    gene_rankings = []
    map_arr = generate_inputs(anno, background)

    for gsid in sample_sets.genesets:
        input_items = multiprocess(gsid, sample_sets, map_arr, hypergeometric_process)
        for input_item in input_items:
            gene_rankings.append(input_item)
    final_rankings = benjamini_hochberg(gene_rankings)
    return [final_rankings, significance_filter(final_rankings, alpha)]


# hypergeometric sub-method for multiprocessing, m_arr contains the parameters
def hypergeometric_process(input_item):
    table = gen_table(input_item.gene_set, input_item.anno_list, input_item.background)

    # in the case of no overlaps
    if table == 0:
        return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list),1.0, 0, 0)
    list_anno_overlaps = table[0][0]
    p_value = stats.hypergeom.sf(table[0][0] - 1, table[0][1] + table[1][1], table[0][1], table[0][0] + table[1][0])

    return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list), p_value, list_anno_overlaps, 0)


# binomial test on 2x2 contingency tables
def binomial(sample_sets, anno, alpha, background):
    gene_rankings = []
    map_arr = generate_inputs(anno, background)
    # construct and analyze contingency tables
    for gsid in sample_sets.genesets:
        input_items = multiprocess(gsid, sample_sets, map_arr, binomial_process)
        for input_item in input_items:
            gene_rankings.append(input_item)
    final_rankings = benjamini_hochberg(gene_rankings)
    return [final_rankings, significance_filter(final_rankings, alpha)]


# binomial sub-method for multiprocessing
def binomial_process(input_item):
    table = gen_table(input_item.gene_set, input_item.anno_list, input_item.background)

    # in the case of no overlaps
    if table == 0:
        return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list), 1.0, 0, 0)
    list_anno_overlaps = table[0][0]
    p_value = stats.binom_test(list_anno_overlaps, len(input_item.gene_set), float(table[0][1]) / (table[1][1] + table[0][1]))

    return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list), p_value, list_anno_overlaps, 0)


# chi squared test on 2x2 contigency tables
def chi_squared(sample_sets, anno, alpha, background):
    gene_rankings = []
    map_arr = generate_inputs(anno, background)
    # construct and analyze contingency tables
    for gsid in sample_sets.genesets:
        input_items = multiprocess(gsid, sample_sets, map_arr, chi_process)
        for input_item in input_items:
            gene_rankings.append(input_item)

    final_rankings = benjamini_hochberg(gene_rankings)
    return [final_rankings, significance_filter(final_rankings, alpha)]


# chi squared sub-method for multiprocessing
def chi_process(input_item):
    table = gen_table(input_item.gene_set, input_item.anno_list, input_item.background)

    # in the case of no overlaps
    if table == 0:
        return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list),1.0, 0, 0)
    list_anno_overlaps = table[0][0]
    p_value = stats.chisquare(table)[1][0]
    return OverrepResult(input_item.gsid, len(input_item.gene_set), input_item.anno_id, len(input_item.anno_list),p_value, list_anno_overlaps, 0)


# wrapper method for integrating parsers and all overrep tests
def over_rep_test(test_name, print_option, background=None):
    sample_sets = GMT(args.gene_sets)
    anno_list = GMT(args.annotation_list)
    if args.background_list is not None:
        background = BACKGROUND([], args.background_list)

    if test_name == "fisher_exact":
        rankings = fisher_exact(sample_sets, anno_list, args.rate, background)
    elif test_name == "chi_squared":
        rankings = chi_squared(sample_sets, anno_list, args.rate, background)
    elif test_name == "binomial":
        rankings = binomial(sample_sets, anno_list, args.rate, background)
    elif test_name == "hypergeometric":
        rankings = hypergeometric(sample_sets, anno_list, args.rate, background)

    # prints out the rankings and significant values
    return OUT(rankings[0], rankings[1], args.output).printout(print_option, False)


# FDR correction for multiple hypothesis testing
def benjamini_hochberg(gene_rankings):
    output = []
    gene_rankings = sorted(gene_rankings, key=lambda line: float(line.p_value))

    prev_bh_value = 0
    for i, E_Result in enumerate(gene_rankings):

        bh_value = E_Result.p_value * len(gene_rankings) / float(i + 1)
        bh_value = min(bh_value, 1)

        # to preserve monotonicity, ensures that comparatively less significant items do not have a more comparatively significant FDR
        if bh_value < prev_bh_value:
            output[i - 1].FDR = bh_value

        E_Result.FDR = bh_value
        output.append(E_Result)
        prev_bh_value = bh_value

    return output


# filters out significant items
def significance_filter(gene_rankings, alpha):
    significant_values = []
    for i, E_Result in enumerate(gene_rankings):
        if E_Result.FDR < alpha:
            significant_values.append(E_Result)

    return significant_values


if __name__ == '__main__':
    from argparse import ArgumentParser

    usage = "usage: %prog [options]"
    parser = ArgumentParser(usage, version="%prog dev-unreleased")

    parser.add_argument(
        "-g",
        "--gene-sets file",
        dest="gene_sets",
        help="gene sets file for comparision",
        metavar=".gmt FILE",
        required=True
    )

    parser.add_argument(
        "-a",
        "--annotations-file",
        dest="annotation_list",
        help="annotation file",
        metavar=".gmt FILE",
        required=True
    )
    parser.add_argument(
        "-b",
        "--background-gene file",
        dest="background_list",
        help="background gene list file for comparision (OPTIONAL)",
        metavar=".txt FILE"
    )

    parser.add_argument(
        "-o",
        "--output-file",
        dest="output",
        help="file to output",
        metavar=".txt FILE",
        required=True
    )
    parser.add_argument(
        "-r",
        "--the alpha level for the test",
        dest="rate",
        help="a decimal for the alpha rate (DEFAULT 0.05)",
        metavar="FLOAT",
        type=float,
        default=0.05)

    args = parser.parse_args()

    #perform a fisher_exact test with a console printout
    over_rep_test("fisher_exact", True)
