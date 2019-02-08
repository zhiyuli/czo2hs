import logging
import os
from datetime import datetime as dt

import pandas as pd
from pandas.io.json import json_normalize

from accounts import CZOHSAccount
from utils import create_hs_res_from_czo_row, get_czo_list_from_csv

from utils_logging import text_emphasis, elapsed_time, log_progress, log_uploaded_file_stats
from settings import LOG_DIR, CZO_ACCOUNTS


def logging_init(_log_file_name):
    """
    Configure environment and logging settings
    :return:
    """
    _log_dir = os.path.dirname(_log_file_name)
    if not os.path.exists(_log_dir):
        os.makedirs(_log_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-5.5s]  %(message)s",
        handlers=[
            logging.FileHandler(_log_file_name),
            logging.StreamHandler()
        ])


def migrate_czo_row(czo_row_dict, row_no=1):
    """
    Create a HS resource from a CZO row dict
    :param czo_row_dict: czo data row dict
    :param row_no: row number
    :return: None
    """
    logging.info(text_emphasis("", char='=', num_char=40))
    dt_start_resource = dt.utcnow()
    logging.info("Start migrating one Resource at UTC {}".format(dt_start_resource))

    mgr_record_dict = create_hs_res_from_czo_row(czo_row_dict, CZO_HS_Account_Obj, index=row_no)

    if mgr_record_dict["success"]:
        progress_dict["success"].append(mgr_record_dict)
    else:
        progress_dict["error"].append(mgr_record_dict)

    # append czo_id vs hs_id to lookup table
    czo_hs_id_lookup_dict = {"czo_id": mgr_record_dict["czo_id"],
                             "hs_id": mgr_record_dict["hs_id"],
                             "success": mgr_record_dict["success"]
                             }

    global czo_hs_id_lookup_df
    czo_hs_id_lookup_df = czo_hs_id_lookup_df.append(czo_hs_id_lookup_dict, ignore_index=True)

    log_uploaded_file_stats(mgr_record_dict)

    elapsed_time(dt_start_resource, prompt_str="Resource Creation Time Elapsed")
    log_progress(progress_dict, "Progress Report", start_time=start_time)


if __name__ == "__main__":

    start_time = dt.utcnow()
    log_file_name = "log_{}.log".format(start_time.strftime("%Y-%m-%d_%H-%M-%S"))
    log_file_path = os.path.join(LOG_DIR, log_file_name)
    logging_init(log_file_path)
    logging.info("Script started at UTC {}".format(start_time.strftime("%Y-%m-%d_%H-%M-%S")))

    CZO_HS_Account_Obj = CZOHSAccount(CZO_ACCOUNTS)

    # What CZO data to migrate
    PROCESS_FIRST_N_ROWS = 0  # N>0: process the first N rows in file "czo.csv"; N=0:all rows; N<0: a specific list of czo_id see CZO_ID_LIST
    CZO_ID_LIST = [5486]  # a list of czo_id if PROCESS_FIRST_N_ROWS < 0
    READ_CZO_ID_LIST_FROM_CSV = False  # replace CZO_ID_LIST by reading a lsit of czo_id from file "czo_hs_id.csv"
    FIRST_N_ITEM_IN_CSV = 0  # process the first N items in CZO_ID_LIST; 0-all items;
    if READ_CZO_ID_LIST_FROM_CSV and PROCESS_FIRST_N_ROWS == -1:
        CZO_ID_LIST = get_czo_list_from_csv(FIRST_N_ITEM_IN_CSV)
    progress_dict = {"error": [], "success": [], "size_uploaded_mb": 0.0, "big_file_list": []}

    czo_hs_id_lookup_df = pd.DataFrame(columns=["czo_id", "hs_id", "success"])

    # TODO investigate nans in dataframe probably just empty values
    czo_data = pd.read_csv("data/czo.csv")

    if PROCESS_FIRST_N_ROWS >= 0:

        logging.info("Processing on first {n} rows (0 - all rows)".format(n=PROCESS_FIRST_N_ROWS))
        for index, row in czo_data.iterrows():
            if PROCESS_FIRST_N_ROWS > 0 and index > PROCESS_FIRST_N_ROWS - 1:
                break
            czo_row_dict = row.to_dict()

            # TODO write directly to csv incrementally instead of storing in dataframe then dumping at end
            # TODO be aware of results_file in the paragraph at the end of this script
            # import csv
            #
            # with open('eggs.csv', 'wb') as csvfile:
            #     spamwriter = csv.writer(csvfile, delimiter=' ',
            #                             quotechar='|', quoting=csv.QUOTE_MINIMAL)
            #
            #     spamwriter.writerow(['Spam'] * 5 + ['Baked Beans'])
            #     spamwriter.writerow(['Spam', 'Lovely Spam', 'Wonderful Spam'])

            migrate_czo_row(czo_row_dict, row_no=index + 1)
    else:
        logging.info("Processing on specific {total_rows} czo_ids".format(total_rows=len(CZO_ID_LIST)))
        logging.info(CZO_ID_LIST)
        for k, cur_czo_id in enumerate(CZO_ID_LIST):
            df_row = czo_data.loc[czo_data['czo_id'] == cur_czo_id]
            czo_row_dict = czo_res_dict = df_row.to_dict(orient='records')[0]  # convert csv row to dict
            migrate_czo_row(czo_row_dict, row_no=k+1)

    log_progress(progress_dict, start_time=start_time)

    success_error = progress_dict["success"] + progress_dict["error"]

    # https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.io.json.json_normalize.html
    df_ref_file_list = json_normalize(success_error, "ref_file_list", ["czo_id", "hs_id"], record_prefix="ref_")

    if (not df_ref_file_list.empty) and df_ref_file_list.shape[0] > 0:
        logging.info(text_emphasis("Summary on Big Ref Files"))
        df_ref_file_list_big_file_filter = df_ref_file_list[(df_ref_file_list.ref_big_file_flag == True) & (df_ref_file_list.ref_file_size_mb > 0)]

        # print(df_ref_file_list.to_string())
        logging.info(df_ref_file_list_big_file_filter.to_string())
        logging.info(df_ref_file_list_big_file_filter.sum(axis=0, skipna=True))

    df_concrete_file_list = json_normalize(success_error, "concrete_file_list", ["czo_id", "hs_id"], record_prefix="concrete_")
    if (not df_concrete_file_list.empty) and df_concrete_file_list.shape[0] > 0:
        logging.info(text_emphasis("Summary on Migrated Concrete Files"))

        df_concrete_file_list_filter = df_concrete_file_list[df_concrete_file_list.concrete_file_size_mb > 0]
        # print(df_concrete_file_list.to_string())
        logging.info(df_concrete_file_list_filter.sum(axis=0, skipna=True))

    logging.info(text_emphasis("Migration Errors"))
    for k, error_item in enumerate(progress_dict["error"]):
        logging.info("{} CZO_ID {} HS_ID {} Error {}".format(k + 1,
                                                             error_item["czo_id"],
                                                             error_item["hs_id"],
                                                             "|".join([err_msg.replace("\n", " ") for err_msg in
                                                                       error_item["error_msg_list"]])))
    logging.info(text_emphasis("CZO_ID <---> HS_ID Lookup Table"))
    logging.info(czo_hs_id_lookup_df.to_string())
    results_file = os.path.join(LOG_DIR, 'lookup_{}.csv'.format(start_time.strftime("%Y-%m-%d_%H-%M-%S")))
    logging.info(text_emphasis("Saving Lookup Table to {}".format(results_file)))

    czo_hs_id_lookup_df.to_csv(results_file, encoding='utf-8', index=False)

    # upload log file and results file to hydroshare
    logging.info(text_emphasis("Uploading log file to HS"))
    hs = CZO_HS_Account_Obj.get_hs_by_czo("default")
    hs_id = hs.createResource("CompositeResource",
                              "czo2hs migration log files {}".format(start_time.strftime("%Y-%m-%d_%H-%M-%S")),
                              )
    file_id = hs.addResourceFile(hs_id, log_file_path)
    file_id = hs.addResourceFile(hs_id, results_file)
    print("Log files uploaded to HS res at {}".format(hs_id))
