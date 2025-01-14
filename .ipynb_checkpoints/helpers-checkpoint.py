from googleapiclient.discovery import build
import warnings
warnings.filterwarnings("ignore")

import nltk
from nltk import tokenize
import os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import collections
from nltk.stem.porter import *
from nltk import word_tokenize
from nltk.util import ngrams
import string
import sys
from resources.readability import Readability
import os
import json
from importlib import reload
import sys
from goose3 import Goose
import unicodedata
import tldextract
import numpy as np

sys.setrecursionlimit(2500)


def getSearchResults(query, numResults):
    my_api_key = "AIzaSyB5j2lTK4tVJsPTWmwXJ5ypn1Hojjh-RdU"
    my_cse_id = "011673657838978336298:dqh43ak8nfj"
    
    service = build("customsearch", "v1", developerKey = my_api_key)
    results = []
    for i in range(0, numResults, 10):
        numres = min(numResults - i, 10)
        result = service.cse().list(q = query, cx = my_cse_id, start = i + 1, num = numres).execute()
        results.append(result['items'])
    return results

def getInfo(searchResults):
    urls = []
    titles = []
    snippets = []
    for result in searchResults:
        for res in result:
            urls.append(res['link'])
            titles.append(res['title'])
            snippets.append(res['snippet'])
    return urls, titles, snippets

def load_LIWC_dictionaries(filepath=os.path.join(os.getcwd(), "resources")):
    cat_dict = {}
    stem_dict = {}
    counts_dict = {}
    with open(os.path.join(filepath, "LIWC2007_English100131.dic")) as raw:
        raw.readline()
        for line in raw:
            if line.strip() == "%":
                break
            line = line.strip().split()
            cat_dict[line[0]] = line[1]
            counts_dict[line[0]] = 0
        for line in raw:
            line = line.strip().split()
            stem_dict[line[0]] = [l.replace("*", "") for l in line[1:]]
    return cat_dict, stem_dict, counts_dict

def LIWC(text, cat_dict, stem_dict, counts_dict):
    for key in counts_dict:
        counts_dict[key] = 0
    tokens = word_tokenize(text)
    WC = len(tokens)
    stemmer = PorterStemmer()
    stemed_tokens = [stemmer.stem(t) for t in tokens]

    # count and percentage
    for stem in stem_dict:
        count = stemed_tokens.count(stem.replace("*", ""))
        if count > 0:
            for cat in stem_dict[stem]:
                counts_dict[cat] += count
    counts_norm = [float(counts_dict[cat]) / WC * 100 for cat in counts_dict]
    cats = [cat_dict[cat] for cat in cat_dict]
    return counts_norm, cats

def subjectivity(text, loaded_model, count_vect, tfidf_transformer):
    X_new_counts = count_vect.transform([text])
    X_new_tfidf = tfidf_transformer.transform(X_new_counts)
    result = loaded_model.predict_proba(X_new_tfidf)
    prob_obj = result[0][0]
    prob_subj = result[0][1]
    return prob_obj, prob_subj

def stuff_LIWC_leftout(text):
    puncs = set(string.punctuation)
    tokens = word_tokenize(text)
    quotes = tokens.count("\"")+tokens.count('``')+tokens.count("''")
    Exclaim = tokens.count("!")
    AllPunc = 0
    for p in puncs:
        AllPunc+=tokens.count(p)
    words_upper = 0
    for w in tokens:
        if w.isupper():
            words_upper+=1
    allcaps = float(words_upper)/len(tokens)
    return (float(quotes)/len(tokens))*100, (float(Exclaim)/len(tokens))*100, (float(AllPunc)/len(tokens))*100, allcaps

def wordlen_and_stop(text):
    with open(os.path.join(os.getcwd(), "resources", "stopwords.txt")) as data:
        stopwords = [w.strip() for w in data]
    set(stopwords)
    words = word_tokenize(text)
    WC = len(words)
    stopwords_in_text = [s for s in words if s in stopwords]
    percent_sws = float(len(stopwords_in_text))/len(words)
    lengths = [len(w) for w in words if w not in stopwords]
    if len(lengths) == 0:
        word_len_avg = 3
    else:
        word_len_avg = float(sum(lengths))/len(lengths)
    return percent_sws, word_len_avg, WC

def readability(text):
    rd = Readability(text)
    fkg_score = rd.FleschKincaidGradeLevel()
    SMOG = rd.SMOGIndex()
    return fkg_score, SMOG

def vadersent(text):
    analyzer = SentimentIntensityAnalyzer()
    vs = analyzer.polarity_scores(text)
    return vs['neg'], vs['neu'], vs['pos']

def POS_features(fn, text):
   # fname = os.path.join(outpath, fn.split(".")[0]+"_tagged.txt")

    pos_tags = ["CC","CD","DT","EX","FW","IN","JJ","JJR","JJS","LS","MD","NN","NNS","NNP","NNPS","PDT","POS","PRP","PRP$","RB","RBR","RBS","RP","SYM","TO","UH","WP$","WRB","VB","VBD","VBG","VBN","VBP","VBZ","WDT","WP"]
    sents = tokenize.sent_tokenize(text)
    counts_norm = []
    allwords = []
    sents = tokenize.sent_tokenize(text)

    #with open(fname, "w") as out:
    for sent in sents:
        words = sent.strip(".").split()
        tags = nltk.pos_tag(words)
        strtags = ["/".join((wt[0],wt[1])) for wt in tags]
        strtags = " ".join(strtags)+" "

    line = strtags
    wordandtag = line.strip().split()
    tags = [wt.split("/")[1] for wt in wordandtag]
    counts = collections.Counter(tags)

    for pt in pos_tags:
        try:
            counts_norm.append(float(counts[pt])/len(tags))
        except:
            counts_norm.append(0)

    return counts_norm

def ttr(text):
    words = text.split()
    dif_words = len(set(words))
    tot_words = len(words)
    if tot_words == 0:
        return 0
    return (float(dif_words)/tot_words)

def bias_lexicon_feats(text, bias, assertives, factives, hedges, implicatives, report_verbs, positive_op, negative_op, wneg, wpos, wneu, sneg, spos, sneu):
    tokens = word_tokenize(text)
    bigrams = [" ".join(bg) for bg in ngrams(tokens, 2)]
    trigrams = [" ".join(tg) for tg in ngrams(tokens, 3)]
    bias_count = float(sum([tokens.count(b) for b in bias]))/len(tokens)
    assertives_count = float(sum([tokens.count(a) for a in assertives]))/len(tokens)
    factives_count = float(sum([tokens.count(f) for f in factives]))/len(tokens)
    hedges_count = sum([tokens.count(h) for h in hedges]) +  sum([bigrams.count(h) for h in hedges]) + sum([trigrams.count(h) for h in hedges])
    hedges_count = float(hedges_count)/len(tokens)
    implicatives_count = float(sum([tokens.count(i) for i in implicatives]))/len(tokens)
    report_verbs_count = float(sum([tokens.count(r) for r in report_verbs]))/len(tokens)
    positive_op_count = float(sum([tokens.count(p) for p in positive_op]))/len(tokens)
    negative_op_count = float(sum([tokens.count(n) for n in negative_op]))/len(tokens)
    wneg_count = float(sum([tokens.count(n) for n in wneg]))/len(tokens)
    wpos_count = float(sum([tokens.count(n) for n in wpos]))/len(tokens)
    wneu_count = float(sum([tokens.count(n) for n in wneu]))/len(tokens)
    sneg_count = float(sum([tokens.count(n) for n in sneg]))/len(tokens)
    spos_count = float(sum([tokens.count(n) for n in spos]))/len(tokens)
    sneu_count = float(sum([tokens.count(n) for n in sneu]))/len(tokens)
    return bias_count, assertives_count, factives_count, hedges_count, implicatives_count, report_verbs_count, positive_op_count, negative_op_count, wneg_count, wpos_count, wneu_count, sneg_count, spos_count, sneu_count

def load_acl13_lexicons():
    with open(os.path.join(os.getcwd(), "resources", "bias-lexicon.txt")) as lex:
        bias = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "assertives.txt")) as lex:
        assertives = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "factives.txt")) as lex:
        factives = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "hedges.txt")) as lex:
        hedges = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "implicatives.txt")) as lex:
        implicatives = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "report_verbs.txt")) as lex:
        report_verbs = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "negative-words.txt")) as lex:
        negative = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "positive-words.txt")) as lex:
        positive = set([l.strip() for l in lex])
    with open(os.path.join(os.getcwd(), "resources", "subjclueslen.txt")) as lex:
        wneg = set([]);wpos = set([]);wneu = set([]);sneg = set([]);spos = set([]);sneu = set([])
        for line in lex:
            line = line.split()
            if line[0] == "type=weaksubj":
                if line[-1] == "priorpolarity=negative":
                    wneg.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=positive":
                    wpos.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=neutral":
                    wneu.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=both":
                    wneg.add(line[2].split("=")[1])
                    wpos.add(line[2].split("=")[1])
            elif line[0] == "type=strongsubj":
                if line[-1] == "priorpolarity=negative":
                    sneg.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=positive":
                    spos.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=neutral":
                    sneu.add(line[2].split("=")[1])
                elif line[-1] == "priorpolarity=both":
                    spos.add(line[2].split("=")[1])
                    sneg.add(line[2].split("=")[1])
    return bias, assertives, factives, hedges, implicatives, report_verbs, positive, negative, wneg, wpos, wneu, sneg, spos, sneu

def make_str(seq):
    strseq = [str(s) for s in seq]
    return strseq

def start(title_text, text, source, cat_dict, stem_dict, counts_dict, loaded_model, count_vect, tfidf_transformer, bias, assertives, factives, hedges, implicatives, report_verbs, positive_op, negative_op, wneg, wpos, wneu, sneg, spos, sneu):
    # Setup path function will create the output directory if it does not exist
   # pos_features_path = setup_path(outpath, "pos_tagged_files")

    #cat_dict, stem_dict, counts_dict = load_LIWC_dictionaries()
    liwc_cats = [cat_dict[cat] for cat in cat_dict]
    pos_tags = ["CC","CD","DT","EX","FW","IN","JJ","JJR","JJS","LS","MD","NN","NNS","NNP","NNPS","PDT","POS","PRP","PRP$","RB","RBR","RBS","RP","SYM","TO","UH","WP$","WRB","VB","VBD","VBG","VBN","VBP","VBZ","WDT","WP"]
    pos_tags_titles = [t+"_title" for t in pos_tags]
    liwc_cats_title = [t+"_title" for t in liwc_cats]
   
    if len(text) == 0:
        raise ValueError("No Text")

    pid = 1

    #source
    #source_code = source_encoding(source)
    
    #body
    quotes, Exclaim, AllPunc, allcaps = stuff_LIWC_leftout(text)
    lex_div = ttr(text)
    counts_norm = POS_features("input", text)
   # counts_norm = [str(c) for c in counts_norm]
    counts_norm_liwc, liwc_cats = LIWC(text, cat_dict, stem_dict, counts_dict)
    #counts_norm_liwc = [str(c) for c in counts_norm_liwc]
    vadneg, vadneu, vadpos = vadersent(text)
    fke, SMOG = readability(text)
    stop, wordlen, WC = wordlen_and_stop(text)
    NB_pobj, NB_psubj = subjectivity(text, loaded_model, count_vect, tfidf_transformer)
    bias_count, assertives_count, factives_count, hedges_count, implicatives_count, report_verbs_count, positive_op_count, negative_op_count, wneg_count, wpos_count, wneu_count, sneg_count, spos_count, sneu_count = bias_lexicon_feats(text, bias, assertives, factives, hedges, implicatives, report_verbs, positive_op, negative_op, wneg, wpos, wneu, sneg, spos, sneu)

    #title
    quotes_titles, Exclaim_titles, AllPunc_titles, allcaps_titles = stuff_LIWC_leftout(title_text)
    lex_div_title = ttr(title_text)
    counts_norm_title = POS_features("input_title", title_text)
   # counts_norm_title = [str(c) for c in counts_norm]
    counts_norm_liwc_title, liwc_cats_title2 = LIWC(title_text, cat_dict, stem_dict, counts_dict)
    #counts_norm_liwc_title = [str(c) for c in counts_norm_liwc_title]
    vadneg_title, vadneu_title, vadpos_title = vadersent(title_text)
    fke_title, SMOG_title = readability(title_text)
    stop_title, wordlen_title, WC_title = wordlen_and_stop(title_text)
    NB_pobj_title, NB_psubj_title = subjectivity(title_text, loaded_model, count_vect, tfidf_transformer)
    bias_count_title, assertives_count_title, factives_count_title, hedges_count_title, implicatives_count_title, report_verbs_count_title, positive_op_count_title, negative_op_count_title, wneg_count_title, wpos_count_title, wneu_count_title, sneg_count_title, spos_count_title, sneu_count_title = bias_lexicon_feats(title_text, bias, assertives, factives, hedges, implicatives, report_verbs, positive_op, negative_op, wneg, wpos, wneu, sneg, spos, sneu)

  #  with open(os.path.join(os.getcwd(), "all_features.csv"), "w") as out:
    #seq =("pid,source_code,bias_count,assertives_count,factives_count,hedges_count,implicatives_count,report_verbs_count,positive_op_count,negative_op_count,wneg_count,wpos_count,wneu_count,sneg_count,spos_count,sneu_count,TTR,vad_neg,vad_neu,vad_pos,FKE,SMOG,stop,wordlen,WC,NB_pobj,NB_psubj,quotes,Exclaim,AllPunc,allcaps",",".join(pos_tags),",".join(liwc_cats), "TTR_title,vad_neg_title,vad_neu_title,vad_pos_title,FKE_title,SMOG_title,stop_title,wordlen_title,WC_title,NB_pobj_title,NB_psubj_title,quotes_title,Exclaim_title,AllPunc_title,allcaps_title",",".join(pos_tags_titles),",".join(liwc_cats_title),"bias_count_title,assertives_count_title,factives_count_title,hedges_count_title,implicatives_count_title,report_verbs_count_title,positive_op_count_title,negative_op_count_title,wneg_count_title,wpos_count_title,wneu_count_title,sneg_count_title,spos_count_title,sneu_count_title")
        #out.write(",".join(seq)+"\n")
    #print(",".join(seq)+"\n")
    seq = [bias_count, assertives_count, factives_count, hedges_count, implicatives_count, report_verbs_count, positive_op_count, negative_op_count, 
           wneg_count, wpos_count, wneu_count, sneg_count, spos_count, sneu_count,
           lex_div,vadneg,vadneu,vadpos,fke,SMOG,stop,wordlen,WC,NB_pobj,NB_psubj,quotes,Exclaim,AllPunc,allcaps]
    seq.extend(counts_norm)
    seq.extend(counts_norm_liwc)
    seq.extend([lex_div_title,vadneg_title,vadneu_title,vadpos_title,fke_title,SMOG_title,stop_title,wordlen_title,WC_title,NB_pobj_title,
                NB_psubj_title,quotes_titles,Exclaim_titles,AllPunc_titles,allcaps_titles])
    seq.extend(counts_norm_title)
    seq.extend(counts_norm_liwc_title)
    seq.extend([bias_count_title, assertives_count_title, factives_count_title, hedges_count_title, implicatives_count_title, report_verbs_count_title,
                positive_op_count_title, negative_op_count_title, wneg_count_title, wpos_count_title, wneu_count_title, sneg_count_title, 
                spos_count_title, sneu_count_title])
    #seq = make_str(seq)
    #feat_str = ",".join(seq)
    #print(feat_str + "\n")
       # out.write(feat_str + "\n")
    print(np.shape(seq))
    return seq
    
def fix(text):
    try:
        text = text.decode("ascii", "ignore")
    except:
        text = text.strip()
        text = text.replace('\n', ' ')
        text = text.replace('\\', '')
        text = text.replace("\r", "")
        text = text.replace("\ufffd'", "")
    return text

def scrape(url):
    g = Goose()
    try:
        article = g.extract(url=url)
    except:
         return "Unexpected error when scraping", sys.exc_info()[0]
    text = fix(article.cleaned_text)
    title = fix(article.title)
    domain = tldextract.extract(url)[1]

    return title, text, domain
        

