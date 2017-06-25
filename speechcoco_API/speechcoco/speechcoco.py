#!usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import json
import shutil
import weakref
import sqlite3
from pprint import pprint

'''
    File name: speechcoco.py
    Author: William N. Havard - Research Intern (LIG - GETALP)
    Date created: 22/03/2017
    Date last modified: 24/06/2017
'''

__author__ = "William N. Havard"
__email__ = "william.havard@gmail.com"

#
# CONSTANTS
#

# Gender
F = "Female"
M = "Male"
FM = ["Female", "Male"]

# Nationality
UK = 'UK'
US = 'US'
UK_US = ['UK', 'US']

# Disfluence
NONE = 'None'
BG = 'Beginning'
MD = 'Middle'
END = 'End'
BG_MD_END = ['Beginning', 'Middle', 'End']


#
#   Timecode Class
#

class Timecode:
    def __init__(self, parent, timecode):
        self.value = timecode
        self._parent = weakref.ref(parent)

    def parse(self, seconds=False):
        """

        :param seconds:
        :return:
        """
        return Timecode.s_parse(self.value, seconds=seconds)

    def toTextgrid(self, output, level=3):
        """

        :param output:
        :param level:
        :return:
        """
        Timecode.s_toTextgrid(self.value, output, self._parent().filename, level)

    @staticmethod
    def _milliToSec(t):
        return (t / 1000)

    @staticmethod
    def updateDuration(duration, speed):
        """

        :param duration:
        :param speed:
        :return:
        """
        return (duration / speed)

    @staticmethod
    def updateTimecodeSpeed(timecode, speed):
        """

        :param timecode:
        :param speed:
        :return:
        """
        updatedTimecode = []
        for code in timecode:
            t = float('{:.4f}'.format((code[0] / speed)))
            cat = code[1]
            value = code[2]
            updatedTimecode.append([t, cat, value])
        return updatedTimecode

    @staticmethod
    def s_parse(timecode, seconds=False):
        """

        :param timecode:
        :param seconds:
        :return:
        """
        # dictionary used to store the different levels of alignments
        alignment = []
        wordAlignment = []
        syllableAlignment = []
        phonemeAlignment = []

        for element in timecode:
            if seconds == True:
                millisecond = Timecode._milliToSec(element[0])
            else:
                millisecond = element[0]
            category = element[1]
            value = element[2]

            if category == "WORD":
                # add the end timecode to the previous word
                if len(wordAlignment) != 0 and len(wordAlignment[-1]) < 3 and wordAlignment[-1]["value"] != "__SIL__":
                    wordAlignment[-1].update({"end": syllableAlignment[-1]["begin"]})
                # add knew word to dict
                wordAlignment.append({"value": value, "begin": millisecond})

            elif category == "SYL":
                # add the end timecode to the previous syllable
                if len(syllableAlignment) != 0 and len(syllableAlignment[-1]) < 3:
                    syllableAlignment[-1].update({"end": millisecond})
                # add knew syllable to dict
                syllableAlignment.append({"value": "", "begin": millisecond})

            elif category == "PHO":
                # add the current phoneme to the last created syllable
                syllableAlignment[-1]["value"] += value
                # add the end timecode to the previous phoneme
                if len(phonemeAlignment) != 0 and len(phonemeAlignment[-1]) < 3:
                    phonemeAlignment[-1].update({"end": millisecond})
                # add new phoneme to dict
                phonemeAlignment.append({"value": value, "begin": millisecond})

            elif category == "SIL":
                # add the end timecode to the last phoneme and syllable
                syllableAlignment[-1].update({"end": millisecond})
                phonemeAlignment[-1].update({"end": millisecond})

                # add silence
                if syllableAlignment[-1]['value'] == '':
                    wordAlignment[-1].update({"end": millisecond})
                    wordAlignment.append({"value": "__SIL__", "begin": millisecond, "end": millisecond})
                else:
                    wordAlignment[-1].update({"end": phonemeAlignment[-1]["begin"]})
                    wordAlignment.append(
                        {"value": "__SIL__", "begin": phonemeAlignment[-1]["begin"], "end": millisecond})

        # remove words, syllables and phonemes if the start time is the same as the end time
        wordAlignment = [w for w in wordAlignment if w['begin'] != w['end']]
        syllableAlignment = [s for s in syllableAlignment if s['begin'] != s['end']]
        phonemeAlignment = [p for p in phonemeAlignment if p['begin'] != p['end']]

        # # add the end timecode to the last word
        if len(wordAlignment[-1]) < 3:
            wordAlignment[-1].update({"end": syllableAlignment[-1]["begin"]})

        # add syllable and phoneme to each word
        for wordTimecode in wordAlignment:
            alignment.append(wordTimecode)
            wordBegin = wordTimecode["begin"]
            wordEnd = wordTimecode["end"]
            # look for the syllables belonging to the word
            for syllableTimecode in syllableAlignment:
                syllableBegin = syllableTimecode["begin"]
                syllableEnd = syllableTimecode["end"]
                if syllableBegin >= wordBegin and syllableEnd <= wordEnd:
                    # look for the phoneme belonging to the syllable
                    for phonemeTimecode in phonemeAlignment:
                        phonemeBegin = phonemeTimecode["begin"]
                        phonemeEnd = phonemeTimecode["end"]
                        if phonemeBegin >= syllableBegin and phonemeEnd <= syllableEnd:
                            if wordTimecode['value'] == '__SIL__':
                                updatedPhonemeTimecode = {'value': '__' + phonemeTimecode["value"] + '__',
                                                          'begin': phonemeTimecode["begin"],
                                                          'end': phonemeTimecode["end"]}
                            else:
                                updatedPhonemeTimecode = phonemeTimecode

                            if "phoneme" not in syllableTimecode.keys():
                                syllableTimecode.update({"phoneme": [updatedPhonemeTimecode]})
                            else:
                                syllableTimecode["phoneme"].append(updatedPhonemeTimecode)

                    # add syllable to the word
                    if "syllable" not in alignment[-1].keys():
                        alignment[-1].update({"syllable": [syllableTimecode]})
                    else:
                        alignment[-1]["syllable"].append(syllableTimecode)
        return alignment

    @staticmethod
    def s_toTextgrid(timecodes, outputDir, wavName, level=3):
        """
        :param timecodes (dict): dict containing the timecodes
        :param level (int): 1 -> word level
                            2 -> syllable level
                            3 -> phoneme level.
                            Levels are cumulative, i.e. 3 includes 1 and 2 ; 2 includes 1
        :return: void
        """

        # create dir
        if os.path.split(outputDir)[0]:
            try:
                os.stat(os.path.split(outputDir)[0])
            except:
                os.makedirs(os.path.split(outputDir)[0])

        if not os.path.split(outputDir)[1]:
            if wavName != '':
                filename = str(wavName).replace('.wav', '.TextGrid')
            else:
                filename = 'TextGridFile.TextGrid'
            outputDir = os.path.split(outputDir)[0] + '/' + filename

        timecodes = Timecode.s_parse(timecodes, seconds=True)

        with open(outputDir, 'w') as f:
            if level < 1:
                level = 3

            # "header" of the TextGrid file
            f.write("File type = \"ooTextFile\"\n")
            f.write("Object class = \"TextGrid\"\n\n")
            f.write("xmin = 0\n")
            f.write("xmax = " + str(timecodes[-1]["end"]) + "\n")
            f.write("tiers? <exists>\n")
            f.write("size = " + str(level) + "\n")
            f.write("item[]:\n")

            # level count
            levelNumber = 1

            # phoneme level
            if level >= 3:
                # get phonemes
                phonemes = [phoneme for words in timecodes for syllables in words["syllable"] for phoneme in
                            syllables["phoneme"]]
                nbTier = len(phonemes)
                f.write("\titem[" + str(levelNumber) + "]:\n")
                f.write("\t\tclass = \"IntervalTier\"\n")
                f.write("\t\tname = \"phonemes\"\n")
                f.write("\t\txmin = 0\n")
                f.write("\t\txmax = " + str(phonemes[-1]["end"]) + "\n")
                f.write("\t\tintervals: size = " + str(nbTier) + "\n")
                for i in range(nbTier):
                    f.write("\t\tintervals [" + str(i + 1) + "]:\n")
                    f.write("\t\t\txmin = " + str(phonemes[i]['begin']) + "\n")
                    f.write("\t\t\txmax = " + str(phonemes[i]['end']) + "\n")
                    f.write("\t\t\ttext = \"" + str(phonemes[i]['value']) + "\"\n")
                levelNumber += 1

            # syllable level
            if level >= 2:
                # get syllables
                syllables = [syllable for word in timecodes for syllable in word["syllable"]]
                nbTier = len(syllables)
                f.write("\titem[" + str(levelNumber) + "]:\n")
                f.write("\t\tclass = \"IntervalTier\"\n")
                f.write("\t\tname = \"syllables\"\n")
                f.write("\t\txmin = 0\n")
                f.write("\t\txmax = " + str(syllables[-1]["end"]) + "\n")
                f.write("\t\tintervals: size = " + str(nbTier) + "\n")
                for i in range(nbTier):
                    f.write("\t\tintervals [" + str(i + 1) + "]:\n")
                    f.write("\t\t\txmin = " + str(syllables[i]['begin']) + "\n")
                    f.write("\t\t\txmax = " + str(syllables[i]['end']) + "\n")
                    f.write("\t\t\ttext = \"" + str(syllables[i]['value']) + "\"\n")
                levelNumber += 1

            # word level
            if level >= 1:
                nbTier = len(timecodes)
                f.write("\titem[" + str(levelNumber) + "]:\n")
                f.write("\t\tclass = \"IntervalTier\"\n")
                f.write("\t\tname = \"words\"\n")
                f.write("\t\txmin = 0\n")
                f.write("\t\txmax = " + str(timecodes[-1]["end"]) + "\n")
                f.write("\t\tintervals: size = " + str(nbTier) + "\n")
                for i in range(nbTier):
                    f.write("\t\tintervals [" + str(i + 1) + "]:\n")
                    f.write("\t\t\txmin = " + str(timecodes[i]['begin']) + "\n")
                    f.write("\t\t\txmax = " + str(timecodes[i]['end']) + "\n")
                    f.write("\t\t\ttext = \"" + str(timecodes[i]['value']) + "\"\n")
                levelNumber += 1


#
# Speaker class
#

class Speaker:
    def __init__(self, info):
        self.name = info['name']
        self.gender = info['gender']
        self.nationality = info['nationality']

    def __str__(self):
        return self.name


#
# Caption class
#

class Caption:
    def __init__(self, speaker, info):
        self.speaker = speaker
        self.captionID = info['captionID']
        self.imageID = info['imageID']
        self.text = info['text']
        self.disfluencyVal = info['disfluencyVal']
        self.disfluencyPos = info['disfluencyPos']
        self.duration = info['duration']
        self.filename = info['wavFilename']
        self.speed = info['speed']
        self.timecode = Timecode(self, json.loads(info['timecode']))

    def __str__(self):
        return self.text

    def getWords(self, begin, end, seconds=True, level=1, olapthr=75):
        return Caption.s_getWords(self.timecode.parse(seconds=seconds), begin, end, level, olapthr)

    @staticmethod
    def s_getWords(parsedTimecode, begin, end, level=1, olapthr=75):
        token = []

        if level < 1:
            level = 3

        for word in parsedTimecode:
            # word level
            if begin <= word['end'] and end >= word['begin']:
                olap = Caption._overlap(begin, end, word['begin'], word['end'])
                if olap >= olapthr:
                    token.append({'word': word['value'].lower(), 'overlapPercentage': olap, 'begin': word['begin'],
                                  'end': word['end']})
                    # syllable level
                    if level >= 2:
                        for syllable in word['syllable']:
                            if begin <= syllable['end'] and end >= syllable['begin']:
                                if 'syllables' not in token[-1].keys():
                                    token[-1].update({'syllables': [{'value': syllable['value'],
                                                                     'overlapPercentage': Caption._overlap(begin, end,
                                                                                                           syllable[
                                                                                                               'begin'],
                                                                                                           syllable[
                                                                                                               'end']),
                                                                     'begin': syllable['begin'],
                                                                     'end': syllable['end']}]})
                                else:
                                    token[-1]['syllables'].append({'value': syllable['value'],
                                                                   'overlapPercentage': Caption._overlap(begin, end,
                                                                                                         syllable[
                                                                                                             'begin'],
                                                                                                         syllable[
                                                                                                             'end']),
                                                                   'begin': syllable['begin'], 'end': syllable['end']})
                                # phoneme level
                                if level >= 3:
                                    for phoneme in syllable['phoneme']:
                                        if begin <= phoneme['end'] and end >= phoneme['begin']:
                                            if 'phonemes' not in token[-1]['syllables'][-1].keys():
                                                token[-1]['syllables'][-1].update({'phonemes': [
                                                    {'value': phoneme['value'],
                                                     'overlapPercentage': Caption._overlap(begin, end, phoneme['begin'],
                                                                                           phoneme['end']),
                                                     'begin': phoneme['begin'], 'end': phoneme['end']}]})
                                            else:
                                                token[-1]['syllables'][-1]['phonemes'].append(
                                                    {'value': phoneme['value'],
                                                     'overlapPercentage': Caption._overlap(begin, end, phoneme['begin'],
                                                                                           phoneme['end']),
                                                     'begin': phoneme['begin'], 'end': phoneme['end']})
        return token

    @staticmethod
    def _overlap(begin, end, goldBegin, goldEnd):
        # code taken from http://stackoverflow.com/questions/2953967/built-in-function-for-computing-overlap-in-python
        return float(max(0, min(end, goldEnd) - max(begin, goldBegin)) / (goldEnd - goldBegin) * 100)


#
# Main class
#

class SpeechCoco:
    #
    #   __init__
    #

    def __init__(self, databaseDir, translationDir='', verbose=False):
        assert os.path.splitext(databaseDir)[1] == ".sqlite3", "Incorrect file format!"
        assert os.stat(databaseDir), "The database doesn't exist!"

        if verbose == True:
            print("|> Loading the database {} ...".format(databaseDir))

        self.database = sqlite3.connect(databaseDir)
        self.database.row_factory = sqlite3.Row
        self.cursor = self.database.cursor()
        # self.cursor.execute("PRAGMA synchronous = OFF;")

        if translationDir != '':
            assert os.stat(translationDir), "The database doesn't exist!"
            self._translationStatus = True
            self.translationDatabase = sqlite3.connect(translationDir)
            self.translationDatabase.row_factory = sqlite3.Row
            self.translationCursor = self.translationDatabase.cursor()
        else:
            self._translationStatus = False

        if verbose == True:
            print("|> Done.")

        self._speakers = dict()
        self._createIndex()
        self._verbose = True

    def _createIndex(self):
        query = 'SELECT * FROM speakers'
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        for row in result:
            self._speakers[row['name']] = Speaker(row)

    def __del__(self):
        self.database.close()
        self.cursor = None
        self.database = None

    #
    #   SPEAKERS
    #

    def getSpeakers(self, nationality=[], gender=[], raw=False):
        """

        :param nationality:
        :param gender:
        :return:
        """
        if type(nationality) is str:
            nationality = [nationality]
        if type(gender) is str:
            gender = [gender]
        speakers = []

        if len(nationality) == len(gender) == 0:
            query = 'SELECT * FROM speakers'
        else:
            query = 'SELECT * FROM speakers WHERE ' + SpeechCoco._buildQuery(nationality=nationality, gender=gender)
        print(query)

        self.cursor.execute(query)
        result = self.cursor.fetchall()

        if self._verbose == True:
            print("|> Query executed!")

        if raw == False:
            for row in result:
                speakers.append(Speaker(row))
            return speakers
        else:
            return result

    #
    #   IMAGES
    #

    def getImgID(self):
        """

        :return:
        """
        query = "SELECT DISTINCT imageID from captions"
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        return [value['imageID'] for value in result]

    def getImgCaptions(self, imgID, raw=False):
        """

        :param imgID:
        :return:
        """
        query = "SELECT * FROM captions WHERE imageID={}".format(imgID)
        self.cursor.execute(query)
        result = self.cursor.fetchall()

        if self._verbose == True:
            print("|> Query executed!")

        if raw == False:
            return [Caption(self._speakers[value['speaker']], value) for value in result]
        else:
            return result

    #
    # CAPTIONS
    #

    def filterCaptions(self, speaker=[], gender=[], disfluencyPos=[], nationality=[], speed=[], text=[],
                       duration=lambda d: d >= 0, raw=False):
        """
        :param speaker:
        :param gender:
        :param disfluencyPos:
        :param nationality:
        :param speed:
        :param duration:
        :return:
        """
        if type(nationality) is str:
            nationality = [nationality]

        if type(disfluencyPos) is str:
            disfluencyPos = [disfluencyPos]

        if type(speaker) is str or type(speaker) is int:
            speaker = [speaker]

        if type(gender) is str:
            gender = [gender]

        if type(text) is str:
            text = [text]

        if type(speed) is int or type(speed) is float:
            speed = [speed]
        query = 'SELECT * FROM captions INNER JOIN speakers ON captions.speaker=speakers.name '

        if len(speaker) != 0 or len(gender) != 0 or len(disfluencyPos) != 0 or len(nationality) != 0 or len(speed) != 0:
            whereQuery = SpeechCoco._buildQuery(speaker=speaker, gender=gender, disfluencyPos=disfluencyPos,
                                                nationality=nationality, speed=speed, text=text)
            query = query + 'WHERE ' + whereQuery

        if self._verbose == True:
            print("|> Querying ... {}".format(query))

        self.cursor.execute(query)
        result = self.cursor.fetchall()

        if self._verbose == True:
            print("|> Query executed!")

        if raw == False:
            return [Caption(self._speakers[value['speaker']], value) for value in result if duration(value['duration'])]
        else:
            return result

    def queryCaptions(self, query, raw=False):
        """
        :param query: user's own SQL query
        :return: results
        """

        if self._verbose == True:
            print("|> Querying ... {}".format(query))

        self.cursor.execute(query)
        result = self.cursor.fetchall()

        if self._verbose == True:
            print("|> Query executed!")

        if raw == False:
            return [Caption(self._speakers[value['speaker']], value) for value in result]
        else:
            return result

    #
    #   TRANSLATIONS
    #

    def getLanguages(self):
        if self._translationStatus == False:
            if self._verbose == True:
                print("|> No translation database specified!")
        else:
            query = 'SELECT name FROM sqlite_master WHERE type="table"'
            self.translationCursor.execute(query)
            result = self.translationCursor.fetchall()
            return [r['name'] for r in result]

    def getTranslation(self, captionID, language):
        assert language, "|> No langage specified!"
        query = "SELECT caption FROM {} WHERE captionID=?"
        self.translationCursor.execute(query.format(language), (captionID,))
        result = self.translationCursor.fetchone()
        return result['caption']

    def getTokens(self, captionID, language):
        assert language, "|> No langage specified!"
        query = "SELECT tokens FROM {} WHERE captionID=?"
        self.translationCursor.execute(query.format(language), (captionID,))
        result = self.translationCursor.fetchone()
        return result['tokens']

    def getPOS(self, captionID, language):
        assert language, "|> No langage specified!"
        query = "SELECT pos FROM {} WHERE captionID=?"
        self.translationCursor.execute(query.format(language), (captionID,))
        result = self.translationCursor.fetchone()
        return result['pos']

    #
    #   STATIC METHODS
    #

    @staticmethod
    def _buildQuery(**kwargs):
        query = []
        for key, value in kwargs.items():
            if value != []:
                if key != 'text':
                    equal = '='
                else:
                    equal = ' LIKE '
                query.append(key + equal + str(' OR ' + key + equal).join('"' + str(item) + '"' for item in value))
        return ' AND '.join("(" + item + ")" for item in query)

    @staticmethod
    def jsonToSQL(dirJsons, mergedFilename='./speechCoco.sqlite3', verbose=False):
        """
        :param dirJsons: directory to the JSON files
        :param mergedFilename: database name
        :return:
        """

        startTime = time.time()
        print("|> Merging ... ")

        # create dir
        if os.path.split(mergedFilename)[0]:
            try:
                os.stat(os.path.split(mergedFilename)[0])
            except:
                os.makedirs(os.path.split(mergedFilename)[0])

        speakers={"Bruce":['US', 'Male'],
                  "Paul": ['UK', 'Male'],
                  "Phil": ['US', 'Male'],
                  "Judith": ['UK', 'Female'],
                  "Elizabeth": ['UK', 'Female'],
                  "Bronwen": ['UK', 'Female'],
                  "Jenny": ['US', 'Female'],
                  "Amanda": ['US', 'Female']}

        # if the database doesn't exist, we create it.
        database = sqlite3.connect(mergedFilename)
        db = database.cursor()

        print("Writing DATA")

        # Speaker Table
        db.execute('CREATE TABLE IF NOT EXISTS speakers (name TEXT PRIMARY KEY, gender TEXT, nationality TEXT)')

        # Caption table
        db.execute(
            'CREATE TABLE IF NOT EXISTS captions (captionID INTEGER PRIMARY KEY, imageID INTEGER, wavFilename TEXT, duration FLOAT, timecode TEXT, disfluencyPos TEXT, disfluencyVal TEXT, speed FLOAT, text TEXT, speaker TEXT)')

        filesInDir = os.listdir(dirJsons)
        for number, files in enumerate(filesInDir):
            if verbose:
                print("\t{}/{} {}".format(number + 1, len(filesInDir), files))

            with open(os.path.join(dirJsons, files)) as jsonFile:
                jsonData = json.load(jsonFile)
                imageInsert = "INSERT INTO captions (captionID, imageID, wavFilename, duration, timecode, disfluencyPos, disfluencyVal, speed, text, speaker) VALUES (?,?,?,?,?,?,?,?,?,?)"
                db.execute(imageInsert, (
                jsonData['captionID'], jsonData['imgID'], jsonData['wavFilename'], jsonData['duration'],
                json.dumps(jsonData['timecode']), jsonData['disfluency'][0], jsonData['disfluency'][1],
                jsonData['speed'], jsonData['synthesisedCaption'], jsonData['speaker']))

                speakerInsertion = 'INSERT OR IGNORE INTO speakers (name, nationality, gender) VALUES (?,?,?)'
                db.execute(speakerInsertion, (jsonData['speaker'], speakers[jsonData['speaker']][0], speakers[jsonData['speaker']][1]))

        database.commit()
        database.close()
        if verbose:
            print("\t{:0.2f}s".format(time.time() - startTime))


if __name__ == '__main__':

    # paths
    baseDir = "./train2014/"
    jsonDir = baseDir + "json/"
    wavDir = baseDir + "wav/"
    transDir = baseDir + "translations/"
    outputTxtGrid = './textgrid/'
    # databases
    translationDB = transDir + "train_translate.sqlite3"
    dbName = baseDir + 'train_2014.sqlite3'

    # lets merge all the JSONs in a directory into a single SQLite database
    # SpeechCoco.jsonToSQL(jsonDir, './'+dbName, verbose=True)

    # create SpeechCoco object
    db = SpeechCoco(dbName, translationDB, verbose=True)

    # Get available languages
    print("\nAvailable languages: {}\n".format(db.getLanguages()))
    print("\nAvailable speakers: {}\n".format([s.name for s in db.getSpeakers()]))

    # filter captions (returns Caption Objects)
    captions = db.filterCaptions(gender="Male", nationality="US", speed=0.9, text='%keys%')
    for caption in captions:
        print('\n{}\t{}\t{}\t{}\t{}\t{}\t\t{}'.format(caption.imageID,
                                                      caption.captionID,
                                                      caption.speaker.name,
                                                      caption.speaker.nationality,
                                                      caption.speed,
                                                      caption.filename,
                                                      caption.text))
        # get words between 0.20s and 0.60s
        pprint(caption.getWords(0.20, 0.60, seconds=True, level=1, olapthr=50))

        # move WAV file to specific dir.
        try:
            os.stat(outputTxtGrid)
        except:
            os.makedirs(outputTxtGrid)
        shutil.copy(os.path.join(wavDir, caption.filename), outputTxtGrid)

        # transform each timecode to a Praat TextGrid file
        caption.timecode.toTextgrid(outputTxtGrid, level=3)

        # Get translations and POS
        print(db.getTranslation(caption.captionID, "ja_google"))
        print(db.getPOS(caption.captionID, "ja_google"))
        print(db.getTranslation(caption.captionID, "ja_excite"))

    # filter captions (returns SQLite Row Objects)
    captions = db.filterCaptions(gender="Male", nationality="US", speed=0.9, text='%keys%', raw=True)
    for caption in captions:
        print('\n{}\t{}\t{}\t{}\t{}\t\t{}'.format(caption['imageID'],
                                                      caption['captionID'],
                                                      caption['speaker'],
                                                      caption['speed'],
                                                      caption['wavFilename'],
                                                      caption['text']))
