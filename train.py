import argparse
import collections
import os
import torch
import torch_temp.data.data_loaders as module_data
import torch_temp.model.loss as module_loss
import torch_temp.model.metrics as module_metric
import torch_temp.model.arch as module_arch
import torch_temp.train.coach as module_train

from torch_temp.utils.parse_config import ConfigParser
from torch_temp.utils.dynamic_lr import DynamicLR

from sacred import Experiment
from sacred.observers import MongoObserver
from torch_temp.experiment.sacred import Sacred
from sacred import SETTINGS

# set multiprocessing
import multiprocessing
multiprocessing.set_start_method('spawn', True)


# Currently the discover sources flag must be set here.
# Please see the issue on github:
# https://github.com/IDSIA/sacred/issues/546
SETTINGS["DISCOVER_SOURCES"] = "dir"
ex = Experiment()
config = None


def main_normal():
    logger = config.get_logger("train")

    # setup data_loader instances
    train_data_loader = config.initialize(
        module_data, config["data"]["loader"])
    valid_data_loader = train_data_loader.split_validation()

    if config["testing"]["do"]:
        test_data_loader = getattr(module_data,
                                   config["data"]["loader"]["type"])(
            config["data"]["loader"]["args"]["data_dir"],
            batch_size=config["testing"]["test_batch_size"],
            shuffle=False,
            validation_split=0.0,
            training=False,
            num_workers=config["data"]["loader"]["args"]["num_workers"]
        )
    else:
        test_data_loader = None

    # build model architecture, then  it to console
    model = config.initialize(module_arch, config["model"]["arch"])
    logger.info(model)

    # get function handles of loss and metrics
    loss = config.initialize(module_loss, config["model"]["loss_function"])
    metrics = [config.initialize(module_metric, met)
               for met in config["metrics"]]

    # build optimizer, learning rate scheduler. delete every
    # lines containing lr_scheduler for disabling scheduler
    trainable_params = filter(lambda p: p.requires_grad, model.parameters())
    optimizer = config.initialize(
        torch.optim, config["optimizer"]["opt"], trainable_params)

    trainer_args = {
        "model": model,
        "loss": loss,
        "metrics": metrics,
        "optimizer": optimizer,
        "config": config,
        "train_data_loader": train_data_loader,
        "valid_data_loader": valid_data_loader,
        "test_data_loader": test_data_loader,
    }

    trainer = config.initialize(
        module_train, config["training"]["trainer"], **trainer_args)
    trainer.train()


@ex.main
def main_sacred():
    main_normal()


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="PyTorch Template")
    args.add_argument("-c", "--config", default=None, type=str,
                      help="config file path (default: None)")
    args.add_argument("-r", "--resume", default=None, type=str,
                      help="path to latest checkpoint (default: None)")
    args.add_argument("-d", "--device", default=None, type=str,
                      help="indices of GPUs to enable (default: all)")

    # custom cli options to modify configuration
    # from default values given in json file.
    CustomArgs = collections.namedtuple("CustomArgs", "flags type target")
    options = [
        CustomArgs(["--lr", "--learning_rate"], type=float,
                   target=("optimizer", "args", "lr")),
        CustomArgs(["--bs", "--batch_size"], type=int,
                   target=("data_loader", "args", "batch_size"))
    ]
    config = ConfigParser(args, options)

    if config["logging"]["sacred_logs"]["do"] is False:
        config.init_logger()
        main_normal()
    else:
        # init logger
        sacred_exp = Sacred(
            ex,
            config=config.config,
            auto_config=True,
        )
        config.init_logger(sacred_ex=sacred_exp.ex)
        ex.run()
