import os
from datetime import datetime
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient
import numpy as np

intents = discord.Intents.default()
intents.members = True
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
client = MongoClient(os.getenv('MONGODB_URL'))
db = client[os.getenv('DB_NAME') or 'jbucks']

bot = commands.Bot('j!', commands.DefaultHelpCommand(no_category="JBucks"), intents=intents)
import user
import jobs
import utils

    # return bot.await utils.get_user(int(user_id)) or await bot.fetch_user(int(user_id))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send('Bad arguments')
    if isinstance(error, commands.CommandInvokeError):
        await ctx.send('Bad arguments')
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have permission to run this command')
    raise error

@bot.command(name='daily', help='print your daily JBuck')
async def daily(ctx):
    juser = user.JUser(ctx.author.id)
    if juser.daily_available:
        await ctx.send(juser.daily())
    else:
        await ctx.send('You are attempting to gain more than ur alloted Jbucks')
    juser.save()

@bot.command(name='pay', help='pay <amount> <@user> <reason?>')
async def pay(ctx, amount: float, target: discord.Member, *reasons):
    juser = user.JUser(ctx.author.id)
    target_user = user.JUser(target.id)
    reason = ' '.join(reasons)

    if amount <= 0:
        await ctx.send('You can only send a positive amount of JBucks')
        return

    if juser.jbucks < amount:
        await ctx.send('You are too poor for this request (You have {} Jbucks)'.format(juser.jbucks))
        return

    await utils.transfer(ctx, juser, ctx.author.mention, target_user, target.mention, amount, reason=reason)

@bot.command(name='viewrequests', brief='viewrequests <type?>',
    help='"posted" to see only your requests; "accepted" to see accepted by you; "all" to see all, including accepted')
async def viewrequests(ctx, mine=None):
    await utils.view(ctx, 'requests', mine)

@bot.command(name='viewservices', brief='viewservices <type?>',
    help='"posted" to see only your services; "accepted" to see accepted by you; "all" to see all, including accepted')
async def viewservices(ctx, mine=None):
    await utils.view(ctx, 'services', mine)

@bot.command(name='postservice', usage='<cost> <never|daily> <name>:<description>',
    brief='postservice <cost> <never|daily> <name>:<description>',
    help='If "never" is set, there is a one-time transfer when the service is accepted.')
async def postservice(ctx, income: float, repeats, *args):
    await postjob(ctx, -1 * income, repeats, *args)

@bot.command(name='postrequest', usage='<income> <never|daily> <name>:<description>',
    brief='postrequest <income> <never|daily> <name>:<description>',
    help='If "never" is set, there is a one-time transfer when the request is accepted.')
async def postjob(ctx, income: float, repeats, *args):
    if repeats not in ['never', 'daily']:
        await ctx.send("Please specify if the job pays once or daily")
        return
    [name, description] = (' '.join(args)).split(':')
    new_job = jobs.Job(db.globals.find_one_and_update({'key': 'job_counter'}, { '$inc': {'value': 1}}).get('value'))
    new_job.income = income
    new_job.repeats = repeats
    new_job.name = name
    new_job.description = description
    new_job.employer = ctx.author.id
    new_job.save()

    embed = discord.Embed()
    embed.add_field(name=name, value=await utils.get_job_output(ctx, new_job))
    await ctx.send('Successfully Added Job', embed=embed)

@bot.command(name='delete', aliases=['deleteservice', 'deleterequest'], help='delete <job_id>')
async def delete(ctx, job_id: int):
    job = db.jobs.find_one({'_id': job_id})
    if not job:
        await ctx.send("Could not find job")
        return

    if job.get('employer') != ctx.author.id:
        await ctx.send("This is not your job")
        return

    if db.jobs.delete_one({'_id': job_id}).deleted_count:
        await ctx.send("Successfully Deleted Job {}".format(job_id))

@bot.command(name='accept', aliases=['acceptjob', 'acceptservice'], help='accept <job_id>')
async def accept(ctx, job_id: int):
    job_doc = db.jobs.find_one({'_id': job_id})
    if not job_doc:
        await ctx.send("Could not find job")
        return

    juser = user.JUser(ctx.author.id)
    juser.save()

    job = jobs.Job()
    job.load(job_doc)

    if job.accepted:
        await ctx.send("Job is already taken")
        return

    employer = await utils.get_user(ctx, job.employer)
    jemployer = user.JUser(employer.id)
    embed = discord.Embed()
    embed.add_field(name=job.name, value=await utils.get_job_output(ctx, job))
    if (job.income <= 0 and juser.jbucks < -1 * job.income):
        await ctx.send('Sorry, you do not have enough jbux for this service (You have {} jbux)'.format(juser.jbucks))
        return
    if (job.income > 0 and jemployer.jbucks < job.income):
        await ctx.send('Sorry, your employer does not have enough jbux to hire you (They have {} jbux)'.format(jemployer.jbucks))
        return

    await ctx.send('Hey {}, {} has accepted your job:'.format(employer.mention if employer else job.employer, ctx.author.mention), embed=embed)

    if job.repeats == 'never':
        await utils.transfer(ctx, user.JUser(job.employer), employer.mention, juser, ctx.author.mention, job.income, job.name, job._id)
    else:
        db.jobs.update_one({'_id': job_id}, {'$set': {'accepted': ctx.author.id}})

@bot.command(name='quit', aliases=['quitjob'], help='quit <job_id>')
async def quitjob(ctx, job_id: int):
    juser = user.JUser(ctx.author.id)
    job_doc = db.jobs.find_one({'_id': job_id})

    if not job_doc:
        await ctx.send("Could not find job")
        return

    job = jobs.Job()
    job.load(job_doc)

    if job.accepted != ctx.author.id:
        await ctx.send("This is not your job")
        return

    juser.save()
    db.jobs.update_one({'_id': job_id}, { '$set': {'accepted': 0}})

    embed = discord.Embed()
    job.accepted = 0
    embed.add_field(name=job.name, value=await utils.get_job_output(ctx, job))
    await ctx.send('You have quit your job:', embed=embed)

@bot.command(name='raffle', help='start a raffle (admin only)')
@commands.has_permissions(administrator=True)
async def raffle(ctx):
    await ctx.send("our grand prize is {} jbux :) isn't that a lot. good job team...".format(round(utils.get_prize_pool(), 2)))
    user_list = []
    ticket_list = []
    for usr in db.user.find({'raffle_tickets': { '$gt': 0 }}):
        user_list.append(await utils.get_user(ctx, usr.get('user_id')))
        ticket_list.append(int(100 * usr.get('raffle_tickets')))
    ticket_list = np.array(ticket_list)
    ticket_list = np.divide(ticket_list, ticket_list.sum())
    await asyncio.sleep(2)

    [first, second, third] = np.random.default_rng().choice(user_list, 3, False, ticket_list)

    await ctx.send('in third place (so close yet so far.....)....')
    await asyncio.sleep(2)
    await ctx.send('{} :) u get half a jbuck. congrat'.format(third.mention))
    third_juser = user.JUser(third.id)
    third_juser.jbucks += .5
    third_juser.save()
    await asyncio.sleep(2)

    await ctx.send('in second place (sorry ur the worst loser here).....')
    await asyncio.sleep(2)
    await ctx.send('{} ! one jbuck for u'.format(second.mention))
    second_juser = user.JUser(second.id)
    second_juser.jbucks += 1
    second_juser.save()
    await asyncio.sleep(2)

    jpp = round(utils.get_prize_pool(), 2)
    await ctx.send('and in first place (the most winner jelly).....')
    await asyncio.sleep(2)
    await ctx.send('{} ^___^ congrat on {} jbuck !! remember to reinvest it into the jellyconomy!'.format(first.mention, jpp))
    first_juser = user.JUser(first.id)
    first_juser.jbucks += jpp
    first_juser.save()

    db.globals.update_one({'key': 'prize_pool'}, { '$set': {'value': 0}})
    db.user.update_many({}, { '$set': {'raffle_tickets': 0}})


@bot.command(name='transactions', help='check your transaction history. j!transactions all for all transactions')
async def transactions(ctx, fil=None):
    filter_dict = {}
    if fil == 'all':
        pass
    else:
        filter_dict['$or'] = [
            {'to': ctx.author.id},
            {'from': ctx.author.id},
        ]

    data = []
    for entry in db.transactions.find(filter_dict).sort('ts', -1):
        to_user = await utils.get_user(ctx, entry.get('to'))
        from_user = await utils.get_user(ctx, entry.get('from'))
        data.append({
            'name':'{}: {}'.format(entry.get('ts'), entry.get('reason')),
            'value': '{}#{} paid {}#{} {} Jbux'.format(from_user.name, from_user.discriminator, to_user.name,
                                                       to_user.discriminator, abs(entry.get('amount'))),
            'inline': False,
        })

    await utils.paginate(ctx, "Transaction History", data)

@bot.command(name='bal', brief='bal <user?>',
    help='check your jbucks balance, or that of a mentioned user')
async def bal(ctx, usr : discord.Member = None):
    if usr:
        juser = user.JUser(usr.id)
        await ctx.send('{}#{}\'s current balance is {} Jbucks'.format(usr.name, usr.discriminator, round(juser.jbucks, 2)))
    else:
        juser = user.JUser(ctx.author.id)
        await ctx.send('Your current balance is {} Jbucks'.format(round(juser.jbucks, 2)))

@bot.command(name='tickets', brief='tickets <user?>',
    help='check your ticket count, or that of a mentioned user')
async def tickets(ctx, usr : discord.Member = None):
    if usr:
        juser = user.JUser(usr.id)
        await ctx.send('{}#{} has {} raffle tickets'.format(usr.name, usr.discriminator, round(juser.raffle_tickets, 2)))
    else:
        juser = user.JUser(ctx.author.id)
        await ctx.send('You have {} raffle tickets'.format(round(juser.raffle_tickets, 2)))

@bot.command(name='prizepool', aliases=['jpp'], help='check prizepool')
async def prizepool(ctx):
    await ctx.send('The current prize pool is {} Jbucks'.format(round(utils.get_prize_pool(), 2)))

@bot.command(name='gift', brief='gift <user> <amt> (admin only)', help='gifts Jbucks to target user (out of thin air) (admin only)')
@commands.has_permissions(administrator=True)
async def gift(ctx, usr: discord.Member, amt: float):
    juser = user.JUser(usr.id)
    juser.jbucks += amt
    juser.save()
    await ctx.send('{} Jbucks have been generously gifted to {}#{} by the Jelly gods'.format(amt, usr.name, usr.discriminator))

@bot.command(name='award', brief='award <user> (admin only)', help='awards all JBucks in prize pool to target user (admin only)')
@commands.has_permissions(administrator=True)
async def award(ctx, usr: discord.Member):
    amt = db.globals.find_one({'key': 'prize_pool'}).get('value', 0)
    if amt > 0:
        juser = user.JUser(usr.id)
        juser.jbucks += amt
        juser.save()

        db.globals.update_one({'key': 'prize_pool'}, { '$set': {'value': 0}})

        await ctx.send('{} Jbucks have been awarded to {}#{} from the prize pool, which is now empty'.format(amt, usr.name, usr.discriminator))

@bot.command(name='loss', brief='we lost colo, give pity jbuck (admin only)')
@commands.has_permissions(administrator=True)
async def loss(ctx):
    db.user.update_many({}, { '$inc': {'jbucks': 1}})
    await ctx.send('you suck but nice try. here\'s a jbuck <:fuck:735993594825146448>')

@bot.command(name='victory', brief='we won colo, so everyon get jbuck (admin only)')
@commands.has_permissions(administrator=True)
async def victory(ctx):
    db.user.update_many({}, { '$inc': {'jbucks': 5}})
    await ctx.send('We won colo! <:mikudab:728469356605866016> Everyone gets five (5) JBux')

@bot.command(name='leaderboard', help='check jbucks leaderboard')
async def leaderboard(ctx):
    data = []
    for entry in db.user.find({}).sort('jbucks', -1):
        usr = await utils.get_user(ctx, entry.get('user_id'))
        data.append({
            'name': '{}#{}'.format(usr.name, usr.discriminator),
            'value': round(entry.get('jbucks'), 2),
            'inline': False
        })

    await utils.paginate(ctx, "The Official Jelly JBucks Leaderboard", data)

if __name__ == '__main__':
    bot.run(TOKEN)
