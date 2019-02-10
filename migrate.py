import logging
import os
import time

import pandas as pd
from pandas.io.json import json_normalize

from accounts import CZOHSAccount
from api_helpers import create_hs_res_from_czo_row
from settings import LOG_DIR, CZO_ACCOUNTS, STOP_AFTER, CLEAR_LOGS
from utils_logging import text_emphasis, elapsed_time, log_uploaded_file_stats


def logging_init():
    """
    Configure environment and logging settings
    :return: string relative log dir and name
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    elif CLEAR_LOGS:
        for _file in os.listdir(LOG_DIR):
            file_path = os.path.join(LOG_DIR, _file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(e)
    # Show hour time of day then use time.time() to ensure newest is always at bottom in folder
    # TODO match this to the lookup_2019-02-09_18-50-18.csv (using hour and time.time) which is exported at migration completion
    log_file_name = "log_{}.log".format(start_time.strftime("%Y-%m-%d_%Hh_{}".format(time.time())))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-5.5s]  %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, log_file_name)),
            logging.StreamHandler()
        ])
    return os.path.join(LOG_DIR, log_file_name)


def migrate_czo_row(czo_row_dict, czo_accounts, row_no=1):
    """
    TODO docstring
    Create a HS resource from a CZO row dict
    :param czo_row_dict:
    :param czo_accounts:
    :param row_no:
    :return:
    """
    global error_status
    _start = time.time()
    # logging.info(text_emphasis("", char='=', num_char=40))

    full_data_item = create_hs_res_from_czo_row(czo_row_dict, czo_accounts, index=row_no)

    if full_data_item["success"]:
        error_status["success"].append(full_data_item)
    else:
        error_status["error"].append(full_data_item)

    czo_hs_id_lookup_dict = {"czo_id": full_data_item["czo_id"],
                             "hs_id": full_data_item["hs_id"],
                             "success": full_data_item["success"]
                             }

    log_uploaded_file_stats(full_data_item)
    logging.info("{} - Success: {} - Error {}".format(elapsed_time(_start, time.time()),
                                                      len(error_status["success"]), len(error_status["error"])))
    return czo_hs_id_lookup_dict


def output_status(success_error, czo_accounts):
    """
    Parse and log the status
    :param: success_error:
    :param: czo_accounts:
    :return:
    """
    # https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.io.json.json_normalize.html
    df_ref_file_list = json_normalize(success_error, "ref_file_list", ["czo_id", "hs_id"], record_prefix="ref_")

    if (not df_ref_file_list.empty) and df_ref_file_list.shape[0] > 0:
        logging.info(text_emphasis("Summary on Big Ref Files"))
        df_ref_file_list_big_file_filter = df_ref_file_list[
            (df_ref_file_list.ref_big_file_flag == True) & (df_ref_file_list.ref_file_size_mb > 0)]

        logging.info(df_ref_file_list_big_file_filter.to_string())
        logging.info(df_ref_file_list_big_file_filter.sum(axis=0, skipna=True))

    df_concrete_file_list = json_normalize(success_error, "concrete_file_list", ["czo_id", "hs_id"],
                                           record_prefix="concrete_")
    if (not df_concrete_file_list.empty) and df_concrete_file_list.shape[0] > 0:
        logging.info(text_emphasis("Summary on Migrated Concrete Files"))

        df_concrete_file_list_filter = df_concrete_file_list[df_concrete_file_list.concrete_file_size_mb > 0]
        logging.info(df_concrete_file_list_filter.sum(axis=0, skipna=True))

    for k, error_item in enumerate(error_status["error"]):

        # TODO split into a variable pre-assignment and make more readable
        logging.info("{} CZO_ID {} HS_ID {} Error {}".format(k + 1,
                                                             error_item["czo_id"],
                                                             error_item["hs_id"],
                                                             "|".join([err_msg.replace("\n", " ") for err_msg in
                                                                       error_item["error_msg_list"]])))
    return czo_accounts.get_hs_by_czo("default")


def main():
    log_file_path = logging_init()
    logging.info("Start migrating at {}".format(start_time.asctime()))

    czo_accounts = CZOHSAccount(CZO_ACCOUNTS)
    czo_hs_id_lookup_df = pd.DataFrame(columns=["czo_id", "hs_id", "success"])
    czo_data = pd.read_csv("data/czo.csv")  # TODO investigate nans in dataframe probably just empty values

    logging.info("Processing on first {} rows (or 399 whichever is less)".format(STOP_AFTER))
    for k, row in czo_data.iterrows():
        czo_row_dict = row.to_dict()
        result = migrate_czo_row(czo_row_dict, czo_accounts, row_no=k + 1)
        czo_hs_id_lookup_df = czo_hs_id_lookup_df.append(result, ignore_index=True)
        print(czo_hs_id_lookup_df)
        if k == STOP_AFTER - 1:
            break

    success_error = error_status["success"] + error_status["error"]
    hs = output_status(success_error, czo_accounts)

    logging.info(czo_hs_id_lookup_df.to_string())

    results_file = os.path.join(LOG_DIR, 'lookup_{}.csv'.format(start_time.strftime("%Y-%m-%d_%H-%M-%S")))
    logging.info("Saving Lookup Table to {}".format(results_file))
    czo_hs_id_lookup_df.to_csv(results_file, encoding='utf-8', index=False)

    hs_id = hs.createResource("CompositeResource",
                              "czo2hs migration log files {}".format(start_time.strftime("%Y-%m-%d_%H-%M-%S")),)
    hs.addResourceFile(hs_id, log_file_path)
    hs.addResourceFile(hs_id, results_file)

    logging.info("Migration log files uploaded to HydroShare with ID {}".format(hs_id))


if __name__ == "__main__":
    # TODO inspect file_naming, util, migrate, api_operations for import best practices and move functions around as necessary
    # TODO instead of logging success for each step, such as Abstract/Keyword/Author updated successfully, make that silent/implicit and ensure that a failure is logged for any failures
    # TODO store time taken in each progress report
    # TODO display final progress report
    # TODO cleanup logging displays and reduce overall logging to be more concise
    # TODO deal with emphasis asterisk text header log messages differently
    # TODO evaluate async (celery or asyncio) for API calls and why termiate needs to be hit twice
    start_time = time
    error_status = {"error": [], "success": [], "size_uploaded_mb": 0.0, "big_file_list": []}
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit ok")
    finally:
        finish_time = time.time()
        logging.info("Total Migration {}".format(elapsed_time(start_time.time(), finish_time)))
