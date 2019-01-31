# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import pandas as pd
from six.moves import cPickle
import time, os, random
import itertools

import torch
from torch.autograd import Variable
import torch.optim as optim
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.modules.loss import NLLLoss, MultiLabelSoftMarginLoss, MultiLabelMarginLoss, BCELoss

import opts
import models
import utils

timeArray = time.localtime(int(time.time()))
timeStamp = time.strftime("%Y%m%d%H%M%S", timeArray)
performance_log_file = timeStamp + "result.csv"

opt = opts.parse_opt()
train_iter, test_iter = utils.loadData(opt)


def train(opt, train_iter, test_iter, verbose=True):
    global_start = time.time()
    logger = utils.getLogger()
    model = models.setup(opt)
    if torch.cuda.is_available():
        model.cuda()
    params = [param for param in model.parameters() if
              param.requires_grad]  # filter(lambda p: p.requires_grad, model.parameters())

    model_info = "; ".join(
        [str(k) + " : " + str(v) for k, v in opt.__dict__.items() if type(v) in (str, int, float, list, bool)])
    logger.info("# parameters:" + str(sum(param.numel() for param in params)))
    logger.info(model_info)

    model.train()
    optimizer = utils.getOptimizer(params, name=opt.optimizer, lr=opt.learning_rate, scheduler=opt.lr_scheduler)
    optimizer.zero_grad()
    loss_fun = F.cross_entropy

    percisions = []
    for i in range(opt.max_epoch):
        for epoch, batch in enumerate(train_iter):
            start = time.time()

            text = batch.text[0] if opt.from_torchtext else batch.text
            predicted = model(text)

            loss = loss_fun(predicted, batch.label)

            loss.backward()
            utils.clip_gradient(optimizer, opt.grad_clip)
            optimizer.step()

            if verbose:
                if torch.cuda.is_available():
                    logger.info("%d iteration %d epoch with loss : %.5f in %.4f seconds" % (
                    i, epoch, loss.cpu().data.numpy()[0], time.time() - start))
                else:
                    logger.info("%d iteration %d epoch with loss : %.5f in %.4f seconds" % (
                    i, epoch, loss.data.numpy()[0], time.time() - start))

        percision = utils.evaluation(model, test_iter, opt.from_torchtext)
        percisions.append(percision)
        if verbose:
            logger.info("%d iteration with percision %.4f" % (i, percision))

    #    while(utils.is_writeable(performance_log_file)):
    df = pd.read_csv(performance_log_file, index_col=0, sep="\t")
    df.loc[model_info, opt.dataset] = max(percisions)
    df.to_csv(performance_log_file, sep="\t")
    logger.info(model_info + " with time :" + str(time.time() - global_start) + " ->" + str(max(percisions)))
    print(model_info + " with time :" + str(time.time() - global_start) + " ->" + str(max(percisions)))


if __name__ == "__main__":

    if not os.path.exists(performance_log_file):
        with open(performance_log_file, "w") as f:
            f.write("argument\n")
            f.close()
    print("gpu : %d" % opt.gpu)

    parameter_pools = {
        "model": ["lstm", "cnn", "kim_cnn", "fasttext"],
        "keep_dropout": [0.1, 0.5, 0.8, 0.9, 1.0],
        "batch_size": [32, 64, 128],
        "learning_rate": [100, 10, 1, 1e-1, 1e-2, 1e-3],
        "optimizer": ["adam"],
        "lr_scheduler": [None]
    }

    pool = [arg for arg in itertools.product(*parameter_pools.values())]
    pool = random.shuffle(pool)
    args = [arg for i, arg in enumerate(pool) if i % 8 == opt.gpu]

    for arg in args:
        for k, v in zip(parameter_pools.keys(), arg):
            opt.__setattr__(k, v)
        train(opt, train_iter, test_iter, verbose=True)
