import os
import datetime
import argparse
import random
import numpy as np
import torch
import logging
import logging.config
from utils.tf_logger import TfLogger

clss = ['Bag', 'Bed', 'Bottle', 'Bowl', 'Chair', 'Clock', 'Dishwasher', 'Display', 'Door', 'Earphone',  # 0-9
        'Faucet', 'Hat', 'Keyboard', 'Knife', 'Lamp', 'Laptop', 'Microwave', 'Mug', 'Refrigerator', 'Scissors',  # 10-19
        'StorageFurniture', 'Table', 'TrashCan', 'Vase']  # 20-23


# level3: 1, 2, 4, 5, 6, 7, 8,9 ; 10, 13, 14, 16, 18 ;  20, 21, 22, 23
class OptInit():
    def __init__(self):
        parser = argparse.ArgumentParser(description='PyTorch implementation of Deep GCN')

        # base
        parser.add_argument('--phase', default='test', type=str, help='train or test(default)')
        parser.add_argument('--use_cpu', action='store_true', help='use cpu?')

        # dataset args
        parser.add_argument('--data_dir', type=str, default='/data/deepgcn/partnet')
        parser.add_argument('--dataset', type=str, default='sem_seg_h5')
        parser.add_argument('--category', type=int, default=18)
        parser.add_argument('--level', type=int, default=3)
        parser.add_argument('--batch_size', default=7, type=int, help='mini-batch size (default:8)')
        parser.add_argument('--test_batch_size', default=12, type=int, help='test mini-batch size (default:12)')
        parser.add_argument('--in_channels', default=3, type=int, help='the channel size of input point cloud ')
        # train args
        parser.add_argument('--total_epochs', default=500, type=int, help='number of total epochs to run')
        parser.add_argument('--iter', default=-1, type=int, help='number of iteration to start')
        parser.add_argument('--lr_adjust_freq', default=50, type=int, help='decay lr after certain number of epoch')
        parser.add_argument('--lr', default=5e-3, type=float, help='initial learning rate')
        parser.add_argument('--lr_decay_rate', default=0.9, type=float, help='learning rate decay')
        parser.add_argument('--postname', type=str, default='', help='postname of saved file')
        parser.add_argument('--multi_gpus', action='store_true', help='use multi-gpus')
        parser.add_argument('--seed', default=0, type=int, help='seed')

        # model args
        parser.add_argument('--pretrained_model', type=str, help='path to pretrained model(default: none)', default='')
        parser.add_argument('--use_ckpt_lr', type=bool, help='use lr of pretrained model', default=True)
        parser.add_argument('--kernel_size', default=10, type=int, help='neighbor num (default:20)')
        parser.add_argument('--block', default='res', type=str, help='graph backbone block type {res, plain, dense}')
        parser.add_argument('--conv', default='edge', type=str, help='graph conv layer {edge, mr}')
        parser.add_argument('--act', default='relu', type=str, help='activation layer {relu, prelu, leakyrelu}')
        parser.add_argument('--norm', default='batch', type=str,
                            help='batch or instance normalization {batch, instance}')
        parser.add_argument('--knn', default='matrix', type=str, help='use matrix or tree')
        parser.add_argument('--bias', default=True, type=bool, help='bias of conv layer True or False')
        parser.add_argument('--n_filters', default=64, type=int, help='number of channels of deep features')
        parser.add_argument('--n_blocks', default=28, type=int, help='number of basic blocks')
        parser.add_argument('--use_dilation', default=True, type=bool, help='use dilated knn or not')
        parser.add_argument('--dropout', default=0.5, type=float, help='ratio of dropout')
        # dilated knn
        parser.add_argument('--epsilon', default=0.2, type=float, help='stochastic epsilon for gcn')
        parser.add_argument('--stochastic', default=True, type=bool, help='stochastic for gcn, True or False')
        # saving
        parser.add_argument('--ckpt_path', type=str, default='')
        parser.add_argument('--save_best_only', action='store_true', help='only save best model')
        args = parser.parse_args()

        args.category_no = args.category
        args.category = clss[args.category]
        dir_path = os.path.dirname(os.path.abspath(__file__))
        args.task = os.path.basename(dir_path)
        args.post = '-'.join([args.task, args.category, args.block, args.conv, 'b' + str(args.n_blocks),
                              'f' + str(args.n_filters),
                              'dil_' + str(args.use_dilation)[0]])
        if args.postname:
            args.post += '-' + args.postname
        args.time = datetime.datetime.now().strftime("%y%m%d")

        if args.pretrained_model:
            if args.pretrained_model[0] != '/':
                args.pretrained_model = os.path.join(dir_path, args.pretrained_model)
        if not args.ckpt_path:
            args.save_path = os.path.join(dir_path, 'checkpoints/ckpts' + '-' + args.post + '-' + args.time)
        else:
            args.save_path = os.path.join(args.ckpt_path, 'checkpoints/ckpts' + '-' + args.post + '-' + args.time)
        args.logdir = os.path.join(dir_path, 'logs/' + args.post + '-' + args.time)

        if args.use_cpu:
            args.device = torch.device('cpu')
        else:
            args.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.args = args

    def initialize(self):
        if self.args.phase == 'train':
            # logger
            self.args.logger = TfLogger(self.args.logdir)
            # loss
            self.args.epoch = -1
            self.make_dir()

        self.set_seed(self.args.seed)
        self.logging_init()
        if self.args.phase == 'train':
            self.print_args()
        return self.args

    def print_args(self):
        self.args.printer.info("==========       CONFIG      =============")
        # print("==========       CONFIG      =============")
        for arg, content in self.args.__dict__.items():
            self.args.printer.info("{}:{}".format(arg, content))
        self.args.printer.info("==========     CONFIG END    =============")
        self.args.printer.info("\n")
        self.args.printer.info('===> Phase is {}.'.format(self.args.phase))

    def logging_init(self):
        if not os.path.exists(self.args.logdir):
            os.makedirs(self.args.logdir)
        ERROR_FORMAT = "%(message)s"
        DEBUG_FORMAT = "%(message)s"
        LOG_CONFIG = {'version': 1,
                      'formatters': {'error': {'format': ERROR_FORMAT},
                                     'debug': {'format': DEBUG_FORMAT}},
                      'handlers': {'console': {'class': 'logging.StreamHandler',
                                               'formatter': 'debug',
                                               'level': logging.DEBUG},
                                   'file': {'class': 'logging.FileHandler',
                                            'filename': os.path.join(self.args.logdir, self.args.post + '.log'),
                                            'formatter': 'debug',
                                            'level': logging.DEBUG}},
                      'root': {'handlers': ('console', 'file'), 'level': 'DEBUG'}
                      }
        logging.config.dictConfig(LOG_CONFIG)
        self.args.printer = logging.getLogger(__name__)

    def make_dir(self):
        # check for folders existence
        if not os.path.exists(self.args.logdir):
            os.makedirs(self.args.logdir)
        if not os.path.exists(self.args.save_path):
            os.makedirs(self.args.save_path)
        if not os.path.exists(self.args.data_dir):
            os.makedirs(self.args.data_dir)

    def set_seed(self, seed=0):
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
