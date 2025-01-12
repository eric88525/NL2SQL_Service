
import numpy as np
import torch
from transformers import AutoTokenizer
from difflib import SequenceMatcher
# from .model.m1_model import M1Model
from .model.m1v2_model import M1Model

from .model.m2_model import M2Model
from .dataset.utils import *
from collections import namedtuple


class SqlModel():
    """The class combine model 1 output and model 2 output to generate SQL commmand"""

    def __init__(self, config):

        self.device = config['device']

        self.m1_tokenizer = AutoTokenizer.from_pretrained(
            config['m1_tokenizer_name_or_path'], additional_special_tokens=['[unused11]', '[unused12]'])
        self.m2_tokenizer = AutoTokenizer.from_pretrained(
            config['m2_tokenizer_name_or_path'])

        self.special_token_id = [self.m1_tokenizer.convert_tokens_to_ids('[unused11]'),
                                self.m1_tokenizer.convert_tokens_to_ids('[unused12]')]

        self.model_1 = M1Model(config['m1_pretrained_model_name'])
        self.model_1.load_state_dict(torch.load(
            config['m1_model_path'], map_location=torch.device('cpu')))

        self.model_2 = M2Model(config['m2_pretrained_model_name'])
        self.model_2.load_state_dict(torch.load(
            config['m2_model_path'], map_location=torch.device('cpu')))

        self.special_token_map = {'text': '[unused11]', 'real': '[unused12]'}
        self.analyze = config['analyze']

        self.conn_map = ['', 'AND', 'OR']
        self.agg_map = ['', 'AVG', 'MAX', 'MIN', 'COUNT', 'SUM']
        self.cond_map = ['>', '<', '=', '!=', '']

    def get_m1_output(self, question, headers):
        """Get model1 output
        Arguments:
            question: str question
            headers: A list contain two list: column list and column type list
                     For example:
                     [
                        ['name', 'age', 'gender'],
                        ['varchar', 'float', 'varchar']
                     ]
        Returns:
            AggModel output in dict data type. The length of 'agg' and 'cond' is equal to column counts
            For example:
            {
                'agg': array([6, 4, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6]),
                'cond': array([4, 4, 4, 0, 0, 4, 4, 4, 4, 4, 4, 4, 4]),
                'conn_op': array(1)
            }
        """
        all_tokens = self.m1_tokenizer.tokenize(question)

        # Append [[SEP], [unused11], text_type_column, [SEP], [unused12], real_type_column] to all_tokens
        # The result is:
        # all_tokens + [[SEP], [unused11], 'name', [SEP], [unused12], 'ege'...]
        for col_name, col_type in zip(headers[0], headers[1]):
            tokens = ['[SEP]', self.special_token_map[col_type]] + \
                self.m1_tokenizer.tokenize(col_name)
            all_tokens.extend(tokens)

        plus = self.m1_tokenizer.encode_plus(
            all_tokens, is_split_into_words=True, return_tensors='pt')
        # Get header token index
        """
        header_idx = []
        for i, token in enumerate(all_tokens):
            if token == self.special_token_map['text'] or token == self.special_token_map['real']:
                # +1 due to we'll add [SEP] token in first index
                header_idx.append(i+1)
        plus['header_idx'] = torch.tensor(
            header_idx).unsqueeze(0).to(self.device)  
        """

        plus['header_idx'] = torch.zeros_like(plus['input_ids'])
        for special_token_id_ in self.special_token_id:
            plus['header_idx'] [plus['input_ids'] == special_token_id_] = 1

        for k in plus.keys():
            plus[k] = plus[k].to(self.device)

        cond_conn_op_pred, conds_ops_pred, agg_pred = self.model_1(**plus)

        result = {}
        result['conn_op'] = torch.argmax(
            cond_conn_op_pred.squeeze(), dim=-1).to('cpu')
        result['agg'] = torch.argmax(
            agg_pred.squeeze(), dim=-1).to('cpu').tolist()
        result['cond'] = torch.argmax(
            conds_ops_pred.squeeze(), dim=-1).to('cpu').tolist()

        return result

    def get_m2_output(self, question, cond):

        plus = self.m2_tokenizer.encode_plus(
            question, cond, return_tensors='pt')

        for k in plus.keys():
            plus[k] = plus[k].to(self.device)

        pred = self.model_2(**plus).squeeze().item()
        return pred

    def m1_to_sql(self, m1_result, headers, question, table, table_name):
        """Convert m1 model output to SQL command
            Arguments:
                headers: A list contains column list and column type list. For example:
                    [
                        ['name', 'age', 'gender'],
                        ['varchar', 'float', 'varchar']
                    ]
                question: A string question.
                m1_result: A dict has agg, cond, conn_op key. For example:
                    {
                        'agg': [6, 4, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                        'cond': [4, 4, 4, 0, 0, 4, 4, 4, 4, 4, 4, 4, 4],
                        'conn_op': a int in  [0, 1, 2]
                    }
                table: Row data of table. For example
                    [['搜房网', 10], ['人人网', 50], ['長榮', 10], ...]
            Returns:
                A string SQL command
        """
        agg, cond, conn_op = m1_result['agg'], m1_result['cond'], self.conn_map[m1_result['conn_op']]

        column_info = namedtuple('headers', ['columns_name', 'columns_type'])
        headers = column_info(columns_name=headers[0], columns_type=headers[1])

        pre = ''
        SELECT_COLUMN = ''

        if self.analyze:
            print('agg result')
            print(f"\tagg: {agg}")
            print(f"\tcond: {cond}")
            print(f"\tconn_op: {conn_op}")

        # If all items in list are 6, not_select = True
        not_select = len(set(agg)) == 1
        # select the column which is most similar to question
        if not_select:
            str_sim = np.zeros(len(agg))
            for i, h in enumerate(headers.columns_name):
                str_sim[i] = SequenceMatcher(None, question, h).ratio()
            agg[np.argmax(str_sim)] = 0

            if self.analyze:
                print(
                    f"agg not select! after fix  = {agg} by {str_sim.tolist()}")

        # SQL SELECT
        for col_idx, val in enumerate(agg):
            if val != 6:
                if headers.columns_type[col_idx] == 'text':
                    SELECT_COLUMN += pre + \
                        f"(`{headers.columns_name[col_idx]}`)"
                else:
                    SELECT_COLUMN += pre + \
                        f"{self.agg_map[val]}(`{headers.columns_name[col_idx]}`)"
                pre = ' ,'

        if self.analyze:
            print(f"SELECT {SELECT_COLUMN}\n\n")

        # where condition
        WHERE_COND = ''

        for col_idx, val in enumerate(cond):
            if val != 4:
                if headers.columns_type[col_idx] == 'text':
                    values_list = set([r[col_idx]
                                      for r in table])  # value from table
                else:
                    values_list = extract_values_from_text(
                        question)  # extract values from question
                    if self.analyze:
                        print(values_list, 'number from question')

                possible_cond = []

                for v in values_list:
                    # format like `apple` > "10" or `name` = "Tom"
                    cond = f"`{headers.columns_name[col_idx]}` {self.cond_map[val]} \"{str(v)}\""
                    m2_format_cond = f"{headers.columns_name[col_idx]}{self.cond_map[val]}{str(v)}"
                    p = self.get_m2_output(question, m2_format_cond)
                    possible_cond.append([cond, p])

                # no where condition, skip to next column
                if len(possible_cond) == 0:
                    continue

                # sort by probability, add condition text
                possible_cond = sorted(
                    possible_cond, key=lambda x: x[1], reverse=True)

                if self.analyze:
                    print('possible_cond')
                    for cond_ in possible_cond:
                        print(cond_)
                # if all cond has low p, pick first
                if possible_cond[0][-1] < 0.4:
                    possible_cond[0][-1] = 1

                # Fix error of more than one condition and conn_op is not AND or OR
                if len(possible_cond) > 1 and conn_op == '':
                    conn_op = 'AND'

                for cond_, p in possible_cond:
                    if p < 0.2:
                        continue
                    if len(WHERE_COND):
                        WHERE_COND += f"{conn_op} {cond_}"
                    else:
                        WHERE_COND += f"{cond_}"

        if self.analyze:
            print(f"WHERE = {WHERE_COND}")
        result = f'SELECT {SELECT_COLUMN} FROM `{table_name}`'

        if WHERE_COND != '':
            result += f" WHERE {WHERE_COND}"

        if self.analyze:
            print(result)

        return result

    def data_to_sql(self, data):
        """Convert input query to SQL command
        Args:
            data: A dict have table_id, question, headers and table.
            For example:
            {
                table_name: 'stock',
                question: '搜房网和人人网的周涨跌幅是多少',
                headers: [['股票名稱', '周漲跌幅'], ['text', 'real']],
                table: [['搜房网', 10], ['人人网', 50], ['長榮', 10], ...]
            }
        """
        m1_result = self.get_m1_output(data["question"], data["headers"])
        result = self.m1_to_sql(m1_result, **data)
        return result
